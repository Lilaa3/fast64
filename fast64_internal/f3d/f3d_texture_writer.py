from typing import Literal, Union, Optional
from dataclasses import dataclass, field
import numpy as np
import copy

import bpy
from math import ceil, floor

from .f3d_enums import *
from .f3d_material import (
    all_combiner_uses,
    calculate_high_mask,
    getTmemWordUsage,
    texBitSizeF3D,
    texFormatOf,
    TextureProperty,
    F3DMaterialProperty,
    isTexturePointSampled,
)
from .f3d_gbi import *
from .f3d_gbi import _DPLoadTextureBlock
from .flipbook import TextureFlipbook

from ..utility import *


def UVtoSTLarge(obj, loopIndex, uv_data, texDimensions):
    uv = uv_data[loopIndex].uv.copy()
    uv[1] = 1 - uv[1]
    loopUV = uv.freeze()

    # Represent the -0.5 texel offset in the UVs themselves in clamping mode
    # if desired, rather than here at export
    pixelOffset = 0
    return [
        convertFloatToFixed16(loopUV[0] * texDimensions[0] - pixelOffset) / 32,
        convertFloatToFixed16(loopUV[1] * texDimensions[1] - pixelOffset) / 32,
    ]


class TileLoad:
    def __init__(self, material, fMaterial, texDimensions):
        self.sl = self.tl = 1000000  # above any actual value
        self.sh = self.th = -1  # below any actual value

        self.texFormat = fMaterial.largeTexFmt
        self.is4bit = texBitSizeInt[self.texFormat] == 4
        self.tmemWordsAvail = fMaterial.largeTexWords
        self.texDimensions = texDimensions
        self.materialName = material.name
        self.isPointSampled = isTexturePointSampled(material)
        self.largeEdges = material.f3d_mat.large_edges

        self.faces = []
        self.offsets = []

    def getLow(self, value, field):
        value = int(floor(value))
        if self.largeEdges == "Clamp":
            value = min(max(value, 0), self.texDimensions[field] - 1)
        if self.is4bit and field == 0:
            # Must start on an even texel (round down)
            value &= ~1
        return value

    def getHigh(self, value, field):
        value = int(ceil(value)) - (1 if self.isPointSampled else 0)
        if self.largeEdges == "Clamp":
            value = min(max(value, 0), self.texDimensions[field] - 1)
        if self.is4bit and field == 0:
            # Must end on an odd texel (round up)
            value |= 1
        return value

    def fixRegion(self, sl, sh, tl, th):
        assert sl <= sh and tl <= th
        soffset = int(floor(sl / self.texDimensions[0])) * self.texDimensions[0]
        toffset = int(floor(tl / self.texDimensions[1])) * self.texDimensions[1]
        sl -= soffset
        sh -= soffset
        tl -= toffset
        th -= toffset
        assert 0 <= sl < self.texDimensions[0] and 0 <= tl < self.texDimensions[1]
        ret = True
        if sh >= 1024 or th >= 1024:
            ret = False
        if sh >= self.texDimensions[0]:
            # Load wraps in S. Load must start a multiple of a TMEM word from
            # the end of the texture, in order for the second load (beginning of
            # image) to start at a whole word.
            texelsPerWord = 64 // texBitSizeInt[self.texFormat]
            if texelsPerWord > self.texDimensions[0]:
                raise PluginError(
                    f"In large texture material {self.materialName}:"
                    + f" large texture must be at least {texelsPerWord} wide."
                )
            sl -= self.texDimensions[0]
            sl = int(floor(sl / texelsPerWord)) * texelsPerWord
            sl += self.texDimensions[0]
        if th >= self.texDimensions[1]:
            # Load wraps in T. Load must start a multiple of 2 texture rows from
            # the end of the texture, in order for the second load to have the
            # same odd/even row parity as the first (because texels are
            # interleaved in TMEM every other row).
            tl -= self.texDimensions[1]
            tl = int(floor(tl / 2.0)) * 2
            tl += self.texDimensions[1]
        tmemUsage = getTmemWordUsage(self.texFormat, sh - sl + 1, th - tl + 1)
        if tmemUsage > self.tmemWordsAvail:
            ret = False
        return ret, sl, sh, tl, th, soffset, toffset

    def initWithFace(self, obj, face):
        uv_data = obj.data.uv_layers["UVMap"].data
        faceUVs = [UVtoSTLarge(obj, loopIndex, uv_data, self.texDimensions) for loopIndex in face.loops]
        if len(faceUVs) == 0:
            return True

        for point in faceUVs:
            self.sl = min(self.sl, self.getLow(point[0], 0))
            self.sh = max(self.sh, self.getHigh(point[0], 0))
            self.tl = min(self.tl, self.getLow(point[1], 1))
            self.th = max(self.th, self.getHigh(point[1], 1))

        ret, self.sl, self.sh, self.tl, self.th, soffset, toffset = self.fixRegion(self.sl, self.sh, self.tl, self.th)
        if not ret:
            if self.sh >= 1024 or self.th >= 1024:
                raise PluginError(
                    f"Large texture material {self.materialName} has a face that needs"
                    + f" to cover texels {self.sl}-{self.sh} x {self.tl}-{self.th}"
                    + f" (image dims are {self.texDimensions}), but image space"
                    + f" only goes up to 1024 so this cannot be represented."
                )
            else:
                raise PluginError(
                    f"Large texture material {self.materialName} has a face that needs"
                    + f" to cover texels {self.sl}-{self.sh} x {self.tl}-{self.th}"
                    + f" ({self.sh-self.sl+1} x {self.th-self.tl+1} texels) "
                    + f"in format {self.texFormat}, which can't fit in TMEM."
                )
        self.faces.append(face)
        self.offsets.append((soffset, toffset))

    def trySubsume(self, other):
        """
        Attempts to enlarge the self TileLoad to cover both itself and the other
        TileLoad. If this succeeds, self is modified and True is returned. If it
        fails (because it would be too large or the other constraints from
        fixRegion would be violated), self is not modified and False is returned.
        A large texture mesh is built by, for each triangle, trying to subsume
        it into each of the existing loads. If it succeeds on one of them, it
        moves on to the next triangle. If it fails on all of them, a new load is
        created for that triangle and added to the list.
        """
        # Could do fancier logic checking across borders, for example if we have
        # one loading 60-68 (size 64) and another 0-8, that could be merged to
        # one load 60-72. But this is likely to be uncommon and won't be generated
        # by the operator.
        new_sl = min(self.sl, other.sl)
        new_sh = max(self.sh, other.sh)
        new_tl = min(self.tl, other.tl)
        new_th = max(self.th, other.th)
        ret, new_sl, new_sh, new_tl, new_th, soffset, toffset = self.fixRegion(new_sl, new_sh, new_tl, new_th)
        if not ret:
            return False
        self.sl, self.sh, self.tl, self.th = new_sl, new_sh, new_tl, new_th
        self.faces.extend(other.faces)
        self.offsets.extend(other.offsets)
        return True


def maybeSaveSingleLargeTextureSetup(
    i: int,
    fMaterial: FMaterial,
    fModel: FModel,
    fImage: FImage,
    gfxOut: GfxList,
    texProp: TextureProperty,
    texDimensions: tuple[int, int],
    tileSettings: TileLoad,
    curImgSet: Optional[int],
    curTileLines: list[int],
):
    """
    Checks whether a particular texture is large and if so, writes the loads for
    that large texture. "maybe" is to bring the if statement into the function
    instead of checking whether the texture is large before calling it.
    """
    if fMaterial.isTexLarge[i]:
        wrapS = tileSettings.sh >= texDimensions[0]
        wrapT = tileSettings.th >= texDimensions[1]
        assert 0 <= tileSettings.sl < texDimensions[0]
        assert 0 <= tileSettings.tl < texDimensions[1]
        siz = texBitSizeF3D[texProp.tex_format]
        line = getTileLine(fImage, tileSettings.sl, tileSettings.sh, siz, fModel.f3d)
        tmem = fMaterial.largeTexAddr[i]
        if wrapS or wrapT:
            fmt = texFormatOf[texProp.tex_format]
            texelsPerWord = 64 // texBitSizeInt[texProp.tex_format]
            wid = texDimensions[0]
            is4bit = siz == "G_IM_SIZ_4b"
            if is4bit:
                siz = "G_IM_SIZ_8b"
                wid >>= 1
                assert (tileSettings.sl & 1) == 0
                assert (tileSettings.sh & 1) == 1
            # TL, TH is always * 4 because tile values are 10.2 fixed.
            # SL, SH is * 2 for 4 bit and * 4 otherwise, because actually loading
            # 8 bit pairs of texels. Also written using f3d.G_TEXTURE_IMAGE_FRAC.
            sm = 2 if is4bit else 4
            nocm = ("G_TX_WRAP", "G_TX_NOMIRROR")
            if curImgSet != i:
                gfxOut.commands.append(DPSetTextureImage(fmt, siz, wid, fImage))

            def loadOneOrTwoS(tmemBase, tidxBase, TL, TH):
                if line != curTileLines[tidxBase]:
                    gfxOut.commands.append(DPSetTile(fmt, siz, line, tmemBase, tidxBase, 0, nocm, 0, 0, nocm, 0, 0))
                    curTileLines[tidxBase] = line
                if wrapS:
                    # Break up at the wrap boundary into two tile loads.
                    # The first load must occupy a whole number of lines.
                    assert (texDimensions[0] - tileSettings.sl) % texelsPerWord == 0
                    sLineOfs = (texDimensions[0] - tileSettings.sl) // texelsPerWord
                    gfxOut.commands.append(
                        DPLoadTile(tidxBase, tileSettings.sl * sm, TL * 4, (texDimensions[0] - 1) * sm, TH * 4)
                    )
                    gfxOut.commands.append(
                        DPSetTile(fmt, siz, line, tmemBase + sLineOfs, tidxBase - 1, 0, nocm, 0, 0, nocm, 0, 0)
                    )
                    curTileLines[tidxBase - 1] = -1
                    gfxOut.commands.append(
                        DPLoadTile(tidxBase - 1, 0, TL * 4, (tileSettings.sh - texDimensions[0]) * sm, TH * 4)
                    )
                else:
                    gfxOut.commands.append(
                        DPLoadTile(tidxBase, tileSettings.sl * sm, TL * 4, tileSettings.sh * sm, TH * 4)
                    )

            if wrapT:
                # Break up at the wrap boundary into two loads.
                # The first load must be even in size (even number of texture rows).
                assert (texDimensions[1] - tileSettings.tl) % 2 == 0
                tLineOfs = line * (texDimensions[1] - tileSettings.tl)
                loadOneOrTwoS(tmem, 7, tileSettings.tl, texDimensions[1] - 1)
                loadOneOrTwoS(tmem + tLineOfs, 5, 0, tileSettings.th - texDimensions[1])
            else:
                loadOneOrTwoS(tmem, 7, tileSettings.tl, tileSettings.th)
            if fMaterial.isTexLarge[i ^ 1]:
                # May reuse any of the above tiles for the other large texture.
                gfxOut.commands.append(DPTileSync())
        else:
            saveTextureLoadOnly(
                fImage,
                gfxOut,
                texProp,
                tileSettings,
                7 - i,
                tmem,
                fModel.f3d,
                curImgSet == i,
                line == curTileLines[7 - i],
            )
            curTileLines[7 - i] = line
        curImgSet = i
        saveTextureTile(
            fImage,
            fMaterial,
            gfxOut,
            texProp,
            tileSettings,
            i,
            tmem,
            fMaterial.texPaletteIndex[i],
            fModel.f3d,
            line == curTileLines[i],
        )
        curTileLines[i] = line
    return curImgSet


# Functions for texture and palette definitions


def getTextureNamesFromBasename(baseName: str, texOrPalFormat: str, parent: Union[FModel, FTexRect], isPalette: bool):
    suffix = getTextureSuffixFromFormat(texOrPalFormat)
    imageName = parent.name + "_" + baseName + "_"
    if isPalette:
        imageName += "pal_"
    imageName += suffix
    imageName = checkDuplicateTextureName(parent, toAlnum(imageName))
    filename = baseName + (f"" if (baseName.endswith(suffix)) else f".{suffix}") + (".pal" if isPalette else ".inc.c")
    return imageName, filename


def getImageName(image: bpy.types.Image):
    if image is None:
        raise PluginError("No image set in material!")
    elif image.filepath == "":
        return image.name
    else:
        return getNameFromPath(image.filepath, True)


def getTextureNamesFromImage(image: bpy.types.Image, texFormat: str, parent: Union[FModel, FTexRect]):
    return getTextureNamesFromBasename(getImageName(image), texFormat, parent, False)


def getTextureNamesFromProp(texProp: TextureProperty, parent: Union[FModel, FTexRect]):
    if texProp.use_tex_reference:
        raise PluginError("Internal error, invalid use of getTextureNamesFromProp")
    return getTextureNamesFromImage(texProp.tex, texProp.tex_format, parent)


def checkDuplicateTextureName(parent: Union[FModel, FTexRect], name):
    names = []
    for info, texture in parent.textures.items():
        names.append(texture.name)
    while name in names:
        name = name + "_copy"
    return name


def saveOrGetPaletteDefinition(
    fMaterial: FMaterial,
    parent: Union[FModel, FTexRect],
    texProp: TextureProperty,
    is_pal_reference: bool,
    images: list[bpy.types.Image],
    palBaseName: str,
    palLen: int,
) -> tuple[FPaletteKey, FImage]:
    texFmt = texProp.tex_format
    palFmt = texProp.ci_format
    palFormat = texFormatOf[palFmt]
    paletteKey = FPaletteKey(palFmt, images)

    if is_pal_reference:
        fPalette = FImage(texProp.pal_reference, None, None, 1, palLen, None)
        return paletteKey, fPalette

    # If palette already loaded, return that data.
    fPalette = parent.getTextureAndHandleShared(paletteKey)
    if fPalette is not None:
        # print(f"Palette already exists")
        return paletteKey, fPalette

    paletteName, filename = getTextureNamesFromBasename(palBaseName, palFmt, parent, True)
    fPalette = FImage(paletteName, palFormat, "G_IM_SIZ_16b", 1, palLen, filename)

    parent.addTexture(paletteKey, fPalette, fMaterial)
    return paletteKey, fPalette


def saveOrGetTextureDefinition(
    fMaterial: FMaterial,
    parent: Union[FModel, FTexRect],
    texProp: TextureProperty,
    images: list[bpy.types.Image],
    isLarge: bool,
) -> tuple[FImageKey, FImage]:
    image = texProp.tex
    texFmt = texProp.tex_format
    texFormat = texFormatOf[texFmt]
    bitSize = texBitSizeF3D[texFmt]
    imageKey = getImageKey(texProp, images)

    if texProp.use_tex_reference:
        width, height = texProp.tex_reference_size
        fImage = FImage(texProp.tex_reference, None, None, width, height, None)
        return imageKey, fImage

    # If image already loaded, return that data.
    fImage = parent.getTextureAndHandleShared(imageKey)
    if fImage is not None:
        # print(f"Image already exists")
        return imageKey, fImage

    imageName, filename = getTextureNamesFromProp(texProp, parent)
    fImage = FImage(imageName, texFormat, bitSize, image.size[0], image.size[1], filename)
    fImage.isLargeTexture = isLarge

    parent.addTexture(imageKey, fImage, fMaterial)
    return imageKey, fImage


@dataclass
class TexInfo:
    load_tex: bool = False
    tex_reference: Optional[str] = None
    texFormat: str = ""
    main_image: Optional[FloatPixelsImage] = None
    _imDependencies: set[FloatPixelsImage] = field(default_factory=set)
    imageDims: tuple[int, int] = (0, 0)

    load_pal: bool = False
    pal_reference: Optional[str] = None
    palFormat: str = ""
    main_pal: Optional[FloatPixelsImage] = None
    _palDependencies: set[FloatPixelsImage] = field(default_factory=set)

    tmemSize: int = 0
    palLen: int = 0

    mirror: tuple[bool, bool] = (False, False)
    clamp: tuple[bool, bool] = (False, False)
    shift: tuple[int, int] = (0, 0)
    low: tuple[float, float] = (0.0, 0.0)
    high: tuple[float, float] = (0.0, 0.0)
    mask: tuple[int, int] = (0, 0)

    # Parameters computed by MultitexManager.writeAll
    texAddr: int = 0
    palAddr: int = 0
    palIndex: int = 0
    palBaseName: str = ""
    doTexTile: bool = True

    # Internal parameters--copies of passed parameters
    texProp: Optional[TextureProperty] = None
    tex: Optional[bpy.types.Image] = None
    indexInMat: int = -1

    @property
    def has_tex(self) -> bool:
        return self.load_tex and self.tex_reference is None

    @property
    def is_ci(self) -> bool:
        return self.texFormat.startswith("CI")

    @property
    def has_pal(self) -> bool:
        return self.is_ci and self.load_pal and self.pal_reference is None

    @property
    def tmem_hash(self):
        values = [self.tex_reference, self.tmemSize, self.texFormat]
        if self.tex_reference is None:
            if self.main_image is not None:
                values.append(self.main_image.name)
        values.append(self.imageDims)
        return hash(tuple(values))

    @property
    def palDependencies(self):
        return {self.main_pal} if self.main_pal is not None else {} | self._palDependencies

    @property
    def imDependencies(self):
        return {self.main_image} if self.main_image is not None else {} | self._imDependencies

    def copy(self):
        new = copy.copy(self)
        new._palDependencies = copy.copy(new._palDependencies)
        new._imDependencies = copy.copy(new._imDependencies)
        return new

    def from_prop(
        self,
        tex_prop: TextureProperty,
        index: int,
        material: bpy.types.Material | None,
        fModel: FModel,
        ignore_tex_set=False,
        base_texture=False,
        pseudo_fmt=False,
    ) -> None:
        if not tex_prop.tex_set and not ignore_tex_set:
            return None
        self.texProp = tex_prop
        self.indexInMat = index

        self.useTex = True
        self.texFormat = "RGBA32" if pseudo_fmt else tex_prop.tex_format
        self.palFormat = tex_prop.ci_format if self.is_ci else ""

        self.values_from_dims(*tex_prop.size)

        self.mirror = (tex_prop.S.mirror, tex_prop.T.mirror)
        self.clamp = (tex_prop.S.clamp, tex_prop.T.clamp)
        self.shift = (tex_prop.S.shift, tex_prop.T.shift)
        self.low = (tex_prop.S.low, tex_prop.T.low)

        self.load_tex = tex_prop.load_tex or base_texture
        self.tex_reference = tex_prop.tex_reference if (tex_prop.use_tex_reference and not base_texture) else None
        img_deps = fModel.gather_images(material, tex_prop, self.tex_reference is not None, base_texture)
        img_deps = set(fModel.gather_pixels(image) for image in img_deps)
        if self.has_tex:
            if len(img_deps) == 1:
                self.main_image = list(img_deps)[0]
            else:
                self._imDependencies = img_deps
        if self.is_ci:
            self.load_pal = tex_prop.load_pal or base_texture
            self.pal_reference = tex_prop.pal_reference if (tex_prop.use_pal_reference and not base_texture) else None
            if self.has_pal:
                if self.has_tex:
                    self._palDependencies = img_deps
                else:
                    if tex_prop.pal is not None:
                        image = tex_prop.pal
                        self.main_pal = fModel.gather_pixels(image)
                        self._palDependencies = {self.main_pal}

        return self

    def values_from_dims(self, width: int, height: int):
        self.imageDims = (width, height)
        self.tmemSize = getTmemWordUsage(self.texFormat, width, height)
        tex_prop = self.texProp
        s_high_mask, t_high_mask = calculate_high_mask(tex_prop.S, width), calculate_high_mask(tex_prop.T, height)
        self.high = (s_high_mask[1], t_high_mask[1])
        self.mask = (s_high_mask[0], t_high_mask[0])

    def error_checking(self):
        if self.has_tex:
            if self.main_image is None:
                raise PluginError("No texture is selected.")
            elif len(self.main_image.pixels) == 0:
                raise PluginError(f"Image {self.tex.name} is missing on disk.")
        if self.imageDims[0] > 1024 or self.imageDims[1] > 1024:
            raise PluginError("Image size (even large textures) limited to 1024 in each dimension.")
        if abs(self.shift[0]) > 10 or abs(self.shift[1]) > 10:
            raise PluginError("Image shift too large.")

    def writeAll(
        self,
        fMaterial: FMaterial,
        fModel: Union[FModel, FTexRect],
        convertTextureData: bool,
    ):
        assert (
            self.imDependencies is not None
        ), "self.imDependencies is None, either moreSetupFromModel or materialless_setup must be called beforehand"

        # Get definitions
        imageKey, fImage = saveOrGetTextureDefinition(
            fMaterial, fModel, self.texProp, self.imDependencies, fMaterial.isTexLarge[self.indexInMat]
        )
        fMaterial.imageKey[self.indexInMat] = imageKey
        if self.load_pal:
            _, fPalette = saveOrGetPaletteDefinition(
                fMaterial,
                fModel,
                self.texProp,
                self.is_pal_reference,
                self.palDependencies,
                self.palBaseName,
                self.palLen,
            )

        # Write loads
        loadGfx = fMaterial.texture_DL
        f3d = fModel.f3d
        if self.load_pal:
            savePaletteLoad(loadGfx, fPalette, self.palFormat, self.palAddr, self.palLen, 5 - self.indexInMat, f3d)
        if self.load_tex:
            saveTextureLoadOnly(fImage, loadGfx, self.texProp, None, 7 - self.indexInMat, self.texAddr, f3d)
        if self.doTexTile:
            saveTextureTile(
                fImage, fMaterial, loadGfx, self.texProp, None, self.indexInMat, self.texAddr, self.palIndex, f3d
            )

        # Write texture data
        if convertTextureData:
            if self.load_pal and not self.is_pal_reference:
                writePaletteData(fPalette, self.pal)
            if self.is_tex_reference:
                if self.is_ci:
                    fModel.writeTexRefCITextures(
                        self.flipbook, fMaterial, self.imDependencies, self.pal, self.texFormat, self.palFormat
                    )
                else:
                    fModel.writeTexRefNonCITextures(self.flipbook, self.texFormat)
            else:
                if self.is_ci:
                    assert (
                        self.pal is not None
                    ), "self.pal is None, either moreSetupFromModel or materialless_setup must be called beforehand"
                    writeCITextureData(self.texProp.tex, fImage, self.pal, self.palFormat, self.texFormat)
                else:
                    writeNonCITextureData(self.texProp.tex, fImage, self.texFormat)


MAX_IMAGES = 8


def shrink_box(pixels: np.ndarray[np.float32, (WIDTH_T, HEIGHT_T, Any)], width_div: int, height_div: int):
    assert width_div > 1 and height_div > 1
    width, height, channels = pixels.shape
    n_width, n_height = width // width_div, height // height_div
    return pixels.reshape(n_width, width_div, n_height, height_div, channels).mean(axis=(1, 3))


YUV_MATRIX = np.array([[0.299, 0.587, 0.114], [-0.14713, -0.28886, 0.436], [0.615, -0.51499, -0.10001]])
WHITE_YUV = np.ones((3,)) @ YUV_MATRIX.T


def ihq_calc_best_i(
    width: int,
    height: int,
    yuv_base: np.ndarray[np.float32, (Any, 3)],
    yuv_target: np.ndarray[np.float32, (Any, 3)],
    ifactor: float,
) -> tuple[np.ndarray[np.float32, (WIDTH_T, HEIGHT_T)], float]:
    yuv_base_ref = yuv_base * (1.0 - ifactor)
    yuv_ifactor = WHITE_YUV * ifactor

    num = np.sum((yuv_target - yuv_base_ref) * yuv_ifactor, axis=1)
    den = np.sum(np.square(yuv_ifactor))
    best_i_flat = np.clip(num / np.maximum(den, 1e-9), 0.0, 1.0)

    final = yuv_base_ref + best_i_flat[:, None] * yuv_ifactor[None, :]
    errs_flat = np.sum((final - yuv_target) ** 2, axis=1)

    return best_i_flat.reshape(width, height), np.sum(errs_flat)


def bilinear_resize(
    pixels: np.ndarray[np.float32, (Any, Any, Any)], width_multiplier: int, height_multiplier: int
) -> np.ndarray[np.float32, (WIDTH_T, HEIGHT_T, Any)]:
    assert (
        width_multiplier > 1 and height_multiplier > 1
    ), "width_multiplier and height_multiplier must be an integer > 1."

    old_width, old_height, _ = pixels.shape
    new_height = old_height * height_multiplier
    new_width = old_width * width_multiplier

    y_new = np.arange(new_height)
    x_new = np.arange(new_width)

    y_old = y_new / height_multiplier  # 1 becomes 0.5
    x_old = x_new / width_multiplier

    # get the top-left integer coordinates
    y0 = np.floor(y_old).astype(np.uint32)
    x0 = np.floor(x_old).astype(np.uint32)

    # get the bottom-right integer coordinates
    y1 = np.clip(y0 + 1, 0, old_height - 1)
    x1 = np.clip(x0 + 1, 0, old_width - 1)

    p00 = pixels[x0, :][:, y0]  # top-left
    p10 = pixels[x1, :][:, y0]  # top-right
    p01 = pixels[x0, :][:, y1]  # bottom-left
    p11 = pixels[x1, :][:, y1]  # bottom-right

    # fractional parts
    yf = y_old - y0
    xf = x_old - x0
    # reshape for broadcasting
    yf = yf.reshape(1, new_height, 1)
    xf = xf.reshape(new_width, 1, 1)

    interp_top = p00 * (1 - xf) + p10 * xf
    interp_bottom = p01 * (1 - xf) + p11 * xf
    new_image = interp_top * (1 - yf) + interp_bottom * yf

    return new_image


def generate_ihq(pixels: FloatPixels):
    width, height, _ = pixels.shape
    if width % 4 != 0 and height % 4 != 0:
        raise ValueError("Image width or height must be a multiple of 4")

    alpha_channel = pixels[:, :, 3]
    color_channels = pixels[:, :, :3]
    uses_alpha = np.any(alpha_channel < 0.5)
    yuv_target = color_channels.reshape(-1, 3) @ YUV_MATRIX.T

    best_err = np.inf
    best_i_pixels, best_rgba_pixels = None, None
    for dir in range(2):
        if dir == 0 and width % 4 == 0:
            width_div, height_div = 4, 2
        elif dir == 1 and height % 4 == 0:
            width_div, height_div = 2, 4
        else:
            assert False, "What the fuck"
        down_scale = shrink_box(pixels, width_div=width_div, height_div=height_div)
        bilinear_upscale = bilinear_resize(
            down_scale[:, :, :3], width_multiplier=width_div, height_multiplier=height_div
        )
        yuv_base = bilinear_upscale.reshape(-1, 3) @ YUV_MATRIX.T
        for ifactor in range(1, 11):
            ifactor *= 0.05
            i_pixels, error = ihq_calc_best_i(width, height, yuv_base, yuv_target, ifactor)

            if error < best_err:
                best_err = error
                if uses_alpha:
                    i_pixels[:, :, 3] = alpha_channel
                best_i_pixels, best_rgba_pixels = i_pixels, down_scale

    return best_i_pixels, best_rgba_pixels, uses_alpha


@dataclass
class MultitexManager:
    is_ci: bool = False
    textures: dict[int, TexInfo] = field(default_factory=dict)
    main_tex: int = 0
    dithering_method: DITHER_MODES = "FLOYD"

    @property
    def mip_levels(self):
        return max((i for i in self.textures.keys()), default=0)

    def __repr__(self):
        return f"MultitexManager(is_ci={self.is_ci}, textures={self.textures}, dithering_method={self.dithering_method}, mip_levels={self.mip_levels})"

    def get_tmem_size(self):
        tmem_size = 0
        added_tex = set()
        for i, tex in self.textures.items():
            tmem_hash = tex.tmem_hash
            if tmem_hash not in added_tex:
                added_tex.add(tmem_hash)
                tmem_size += tex.tmemSize
        return tmem_size

    def generate_mipmaps(self, fModel: FModel):
        tmem_size = self.get_tmem_size()
        prev, mips = None, 0
        for i in range(MAX_IMAGES):
            if i in self.textures:
                prev, mips = self.textures[i], 0
                continue
            elif prev is None:
                continue
            divisor = (mips + 1) * 2
            assert prev.main_image is not None, "prev.main_image is None"
            width, height = prev.imageDims
            n_width, n_height = width // divisor, height // divisor
            if (n_width < 4) or (n_height < 4):
                break
            tmem_size += getTmemWordUsage(prev.texFormat, n_width, n_height)
            if tmem_size >= 256 * (1 if self.is_ci else 2):
                break

            new = prev.copy()
            new.main_image = FloatPixelsImage(
                prev.main_image.name + f"_mip{mips}", shrink_box(prev.main_image.pixels, divisor, divisor)
            )
            # print(n_width, n_height, new.main_image.pixels)
            if prev.main_image == prev.main_pal:
                new.main_pal = new.main_image
            new.values_from_dims(n_width, n_height)
            new.indexInMat = i
            self.textures[i] = new
            divisor *= 2

    def generate_ihq(self):
        assert len(self.textures) == 1 and list(self.textures.keys())[0] == 0
        base_tex = list(self.textures.values())[0]
        rgba_tex = base_tex.copy()

        intensity, rgba, uses_alpha = generate_ihq(base_tex.main_image.pixels)
        base_tex.main_image = FloatPixelsImage(base_tex.main_image.name + "_ihq_i", intensity)
        base_tex.texFormat = "IA4" if uses_alpha else "I4"
        base_tex.values_from_dims(intensity.shape[0], intensity.shape[1])

        rgba_tex.main_image = FloatPixelsImage(rgba_tex.main_image.name + "_ihq_rgba", rgba)
        rgba_tex.texFormat = "RGBA16"
        rgba_tex.shift = (rgba_tex.shift[0] + 1, rgba_tex.shift[1] + 1)
        if rgba_tex.shift[0] > 10 or rgba_tex.shift[1] > 10:
            raise PluginError("Shift is too large for IHQ.")
        rgba_tex.values_from_dims(rgba.shape[0], rgba.shape[1])
        rgba_tex.indexInMat = 1
        self.textures[1] = rgba_tex

    def from_mat(self, mat: bpy.types.Material, pseudo_format: str, f_material: FMaterial, fModel: FModel):
        f3d_mat: "F3DMaterialProperty" = mat.f3d_mat
        self.is_ci = f3d_mat.is_ci
        for i, tex_prop in f3d_mat.set_textures.items():
            tex = TexInfo()
            tex.from_prop(tex_prop, i, mat, fModel, False, False, pseudo_format != "NONE")
            self.textures[i] = tex

    def convert():
        pass

    def getTexDimensions(self):
        return self.texDimensions


# Functions for writing texture and palette DLs


def getTileSizeSettings(texProp: TextureProperty, tileSettings: Optional[TileLoad], f3d: F3D):
    if tileSettings is not None:
        SL = tileSettings.sl
        TL = tileSettings.tl
        SH = tileSettings.sh
        TH = tileSettings.th
    else:
        SL = texProp.S.low
        TL = texProp.T.low
        SH = texProp.S.high
        TH = texProp.T.high
    sl = int(SL * (2**f3d.G_TEXTURE_IMAGE_FRAC))
    tl = int(TL * (2**f3d.G_TEXTURE_IMAGE_FRAC))
    sh = int(SH * (2**f3d.G_TEXTURE_IMAGE_FRAC))
    th = int(TH * (2**f3d.G_TEXTURE_IMAGE_FRAC))
    return SL, TL, SH, TH, sl, tl, sh, th


def getTileLine(fImage: FImage, SL: int, SH: int, siz: str, f3d: F3D):
    width = int(SH - SL + 1) if fImage.isLargeTexture else int(fImage.width)
    if siz == "G_IM_SIZ_4b":
        line = (((width + 1) >> 1) + 7) >> 3
    else:
        # Note that _LINE_BYTES and _TILE_BYTES variables are the same.
        line = int((width * f3d.G_IM_SIZ_VARS[siz + "_LINE_BYTES"]) + 7) >> 3
    return line


def canUseLoadBlock(fImage: FImage, tex_format: str, f3d: F3D):
    if fImage.isLargeTexture:
        return False
    width, height = fImage.width, fImage.height
    texelsPerWord = 64 // texBitSizeInt[tex_format]
    if width % texelsPerWord != 0:
        return False
    wordsperrow = width // texelsPerWord
    dxt = ((1 << f3d.G_TX_DXT_FRAC) + wordsperrow - 1) // wordsperrow
    error = (dxt * wordsperrow) - (1 << f3d.G_TX_DXT_FRAC)
    assert error >= 0
    if error == 0:
        return True
    rowsWhenCorruptionHappens = (dxt + error - 1) // error
    return height < rowsWhenCorruptionHappens


def saveTextureLoadOnly(
    fImage: FImage,
    gfxOut: GfxList,
    texProp: TextureProperty,
    tileSettings: Optional[TileLoad],
    loadtile: int,
    tmem: int,
    f3d: F3D,
    omitSetTextureImage=False,
    omitSetTile=False,
):
    fmt = texFormatOf[texProp.tex_format]
    siz = texBitSizeF3D[texProp.tex_format]
    nocm = ("G_TX_WRAP", "G_TX_NOMIRROR")
    SL, TL, SH, TH, sl, tl, sh, th = getTileSizeSettings(texProp, tileSettings, f3d)

    # LoadTile will pad rows to 64 bit word alignment, while
    # LoadBlock assumes this is already done.
    useLoadBlock = canUseLoadBlock(fImage, texProp.tex_format, f3d)
    line = 0 if useLoadBlock else getTileLine(fImage, SL, SH, siz, f3d)
    wid = 1 if useLoadBlock else fImage.width

    if siz == "G_IM_SIZ_4b":
        if useLoadBlock:
            dxs = (((fImage.width) * (fImage.height) + 3) >> 2) - 1
            dxt = f3d.CALC_DXT_4b(fImage.width)
            siz = "G_IM_SIZ_16b"
            loadCommand = DPLoadBlock(loadtile, 0, 0, dxs, dxt)
        else:
            sl2 = int(SL * (2 ** (f3d.G_TEXTURE_IMAGE_FRAC - 1)))
            sh2 = int(SH * (2 ** (f3d.G_TEXTURE_IMAGE_FRAC - 1)))
            siz = "G_IM_SIZ_8b"
            wid >>= 1
            loadCommand = DPLoadTile(loadtile, sl2, tl, sh2, th)
    else:
        if useLoadBlock:
            dxs = (
                ((fImage.width) * (fImage.height) + f3d.G_IM_SIZ_VARS[siz + "_INCR"])
                >> f3d.G_IM_SIZ_VARS[siz + "_SHIFT"]
            ) - 1
            dxt = f3d.CALC_DXT(fImage.width, f3d.G_IM_SIZ_VARS[siz + "_BYTES"])
            siz += "_LOAD_BLOCK"
            loadCommand = DPLoadBlock(loadtile, 0, 0, dxs, dxt)
        else:
            loadCommand = DPLoadTile(loadtile, sl, tl, sh, th)

    if not omitSetTextureImage:
        gfxOut.commands.append(DPSetTextureImage(fmt, siz, wid, fImage))
    if not omitSetTile:
        gfxOut.commands.append(DPSetTile(fmt, siz, line, tmem, loadtile, 0, nocm, 0, 0, nocm, 0, 0))
    gfxOut.commands.append(loadCommand)


def saveTextureTile(
    fImage: FImage,
    fMaterial: FMaterial,
    gfxOut: GfxList,
    texProp: TextureProperty,
    tileSettings,
    rendertile: int,
    tmem: int,
    pal: int,
    f3d: F3D,
    omitSetTile=False,
):
    if tileSettings is not None:
        clamp_S = True
        clamp_T = True
        mirror_S = False
        mirror_T = False
        mask_S = 0
        mask_T = 0
        shift_S = 0
        shift_T = 0
    else:
        clamp_S = texProp.S.clamp
        clamp_T = texProp.T.clamp
        mirror_S = texProp.S.mirror
        mirror_T = texProp.T.mirror
        mask_S = texProp.S.mask
        mask_T = texProp.T.mask
        shift_S = texProp.S.shift
        shift_T = texProp.T.shift
    cms = (("G_TX_CLAMP" if clamp_S else "G_TX_WRAP"), ("G_TX_MIRROR" if mirror_S else "G_TX_NOMIRROR"))
    cmt = (("G_TX_CLAMP" if clamp_T else "G_TX_WRAP"), ("G_TX_MIRROR" if mirror_T else "G_TX_NOMIRROR"))
    masks = mask_S
    maskt = mask_T
    shifts = shift_S if shift_S >= 0 else (shift_S + 16)
    shiftt = shift_T if shift_T >= 0 else (shift_T + 16)
    fmt = texFormatOf[texProp.tex_format]
    siz = texBitSizeF3D[texProp.tex_format]
    SL, _, SH, _, sl, tl, sh, th = getTileSizeSettings(texProp, tileSettings, f3d)
    line = getTileLine(fImage, SL, SH, siz, f3d)

    tileCommand = DPSetTile(fmt, siz, line, tmem, rendertile, pal, cmt, maskt, shiftt, cms, masks, shifts)
    tileSizeCommand = DPSetTileSize(rendertile, sl, tl, sh, th)

    scrollInfo = fMaterial.scrollData.tile_scrolls[rendertile]
    if scrollInfo.s or scrollInfo.t:
        tileSizeCommand.tags |= GfxTag.TileScroll0 if rendertile == 0 else GfxTag.TileScroll1

    tileSizeCommand.fMaterial = fMaterial
    if not omitSetTile:
        gfxOut.commands.append(tileCommand)
    gfxOut.commands.append(tileSizeCommand)

    # hasattr check for FTexRect
    if hasattr(fMaterial, "tileSizeCommands"):
        fMaterial.tileSizeCommands[rendertile] = tileSizeCommand


# palAddr is the address within the second half of tmem (0-255), normally 16*palette num
# palLen is the number of colors
def savePaletteLoad(
    gfxOut: GfxList,
    fPalette: FImage,
    palFormat: str,
    palAddr: int,
    palLen: int,
    loadtile: int,
    f3d: F3D,
):
    assert 0 <= palAddr < 256 and (palAddr & 0xF) == 0
    palFmt = texFormatOf[palFormat]
    nocm = ("G_TX_WRAP", "G_TX_NOMIRROR")
    gfxOut.commands.extend(
        [
            DPSetTextureImage(palFmt, "G_IM_SIZ_16b", 1, fPalette),
            DPSetTile("0", "0", 0, 256 + palAddr, loadtile, 0, nocm, 0, 0, nocm, 0, 0),
            DPLoadTLUTCmd(loadtile, palLen - 1),
        ]
    )


# Functions for converting and writing texture and palette data


def extractConvertCIPixel(image, pixels, i, j, palFormat):
    color = [1, 1, 1, 1]
    for field in range(image.channels):
        color[field] = pixels[(j * image.size[0] + i) * image.channels + field]
    if palFormat == "RGBA16":
        pixelColor = getRGBA16Tuple(color)
    elif palFormat == "IA16":
        pixelColor = getIA16Tuple(color)
    else:
        raise PluginError("Internal error, palette format is " + palFormat)
    return pixelColor


def getColorsUsedInImage(image, palFormat):
    palette = []
    # N64 is -Y, Blender is +Y
    pixels = image.pixels[:]
    for j in reversed(range(image.size[1])):
        for i in range(image.size[0]):
            pixelColor = extractConvertCIPixel(image, pixels, i, j, palFormat)
            if pixelColor not in palette:
                palette.append(pixelColor)
    return palette


def mergePalettes(pal0, pal1):
    palette = [c for c in pal0]
    for c in pal1:
        if c not in palette:
            palette.append(c)
    return palette


def getColorIndicesOfTexture(image, palette, palFormat):
    texture = []
    # N64 is -Y, Blender is +Y
    pixels = image.pixels[:]
    for j in reversed(range(image.size[1])):
        for i in range(image.size[0]):
            pixelColor = extractConvertCIPixel(image, pixels, i, j, palFormat)
            if pixelColor not in palette:
                raise PluginError(f"Bug: {image.name} palette len {len(palette)} missing CI")
            texture.append(palette.index(pixelColor))
    return texture


def compactNibbleArray(texture, width, height):
    nibbleData = bytearray(0)
    dataSize = int(width * height / 2)

    nibbleData = [((texture[i * 2] & 0xF) << 4) | (texture[i * 2 + 1] & 0xF) for i in range(dataSize)]

    if (width * height) % 2 == 1:
        nibbleData.append((texture[-1] & 0xF) << 4)

    return bytearray(nibbleData)


def writePaletteData(fPalette: FImage, palette: list[int]):
    if fPalette.converted:
        return
    for color in palette:
        fPalette.data.extend(color.to_bytes(2, "big"))
    fPalette.converted = True


def writeCITextureData(
    image: bpy.types.Image,
    fImage: FImage,
    palette: list[int],
    palFmt: str,
    texFmt: str,
):
    if fImage.converted:
        return

    texture = getColorIndicesOfTexture(image, palette, palFmt)

    if texFmt == "CI4":
        fImage.data = compactNibbleArray(texture, image.size[0], image.size[1])
    else:
        fImage.data = bytearray(texture)
    fImage.converted = True


def writeNonCITextureData(image: bpy.types.Image, fImage: FImage, texFmt: str):
    if fImage.converted:
        return
    fmt = texFormatOf[texFmt]
    bitSize = texBitSizeF3D[texFmt]

    pixels = image.pixels[:]
    if fmt == "G_IM_FMT_RGBA":
        if bitSize == "G_IM_SIZ_16b":
            fImage.data = bytearray(
                [
                    byteVal
                    for doubleByte in [
                        (
                            (
                                ((int(round(pixels[(j * image.size[0] + i) * image.channels + 0] * 0x1F)) & 0x1F) << 3)
                                | (
                                    (int(round(pixels[(j * image.size[0] + i) * image.channels + 1] * 0x1F)) & 0x1F)
                                    >> 2
                                )
                            ),
                            (
                                ((int(round(pixels[(j * image.size[0] + i) * image.channels + 1] * 0x1F)) & 0x03) << 6)
                                | (
                                    (int(round(pixels[(j * image.size[0] + i) * image.channels + 2] * 0x1F)) & 0x1F)
                                    << 1
                                )
                                | (1 if pixels[(j * image.size[0] + i) * image.channels + 3] > 0.5 else 0)
                            ),
                        )
                        for j in reversed(range(image.size[1]))
                        for i in range(image.size[0])
                    ]
                    for byteVal in doubleByte
                ]
            )
        elif bitSize == "G_IM_SIZ_32b":
            fImage.data = bytearray(
                [
                    int(round(pixels[(j * image.size[0] + i) * image.channels + field] * 0xFF)) & 0xFF
                    for j in reversed(range(image.size[1]))
                    for i in range(image.size[0])
                    for field in range(image.channels)
                ]
            )
        else:
            raise PluginError("Invalid combo: " + fmt + ", " + bitSize)

    elif fmt == "G_IM_FMT_YUV":
        raise PluginError("YUV not yet implemented.")
        if bitSize == "G_IM_SIZ_16b":
            pass
        else:
            raise PluginError("Invalid combo: " + fmt + ", " + bitSize)

    elif fmt == "G_IM_FMT_CI":
        raise PluginError("Internal error, writeNonCITextureData called for CI image.")

    elif fmt == "G_IM_FMT_IA":
        if bitSize == "G_IM_SIZ_4b":
            fImage.data = bytearray(
                [
                    (
                        (
                            int(
                                round(
                                    colorToLuminance(
                                        pixels[
                                            (j * image.size[0] + i)
                                            * image.channels : (j * image.size[0] + i)
                                            * image.channels
                                            + 3
                                        ]
                                    )
                                    * 0x7
                                )
                            )
                            & 0x7
                        )
                        << 1
                    )
                    | (1 if pixels[(j * image.size[0] + i) * image.channels + 3] > 0.5 else 0)
                    for j in reversed(range(image.size[1]))
                    for i in range(image.size[0])
                ]
            )
        elif bitSize == "G_IM_SIZ_8b":
            fImage.data = bytearray(
                [
                    (
                        (
                            int(
                                round(
                                    colorToLuminance(
                                        pixels[
                                            (j * image.size[0] + i)
                                            * image.channels : (j * image.size[0] + i)
                                            * image.channels
                                            + 3
                                        ]
                                    )
                                    * 0xF
                                )
                            )
                            & 0xF
                        )
                        << 4
                    )
                    | (int(round(pixels[(j * image.size[0] + i) * image.channels + 3] * 0xF)) & 0xF)
                    for j in reversed(range(image.size[1]))
                    for i in range(image.size[0])
                ]
            )
        elif bitSize == "G_IM_SIZ_16b":
            fImage.data = bytearray(
                [
                    byteVal
                    for doubleByte in [
                        (
                            int(
                                round(
                                    colorToLuminance(
                                        pixels[
                                            (j * image.size[0] + i)
                                            * image.channels : (j * image.size[0] + i)
                                            * image.channels
                                            + 3
                                        ]
                                    )
                                    * 0xFF
                                )
                            )
                            & 0xFF,
                            int(round(pixels[(j * image.size[0] + i) * image.channels + 3] * 0xFF)) & 0xFF,
                        )
                        for j in reversed(range(image.size[1]))
                        for i in range(image.size[0])
                    ]
                    for byteVal in doubleByte
                ]
            )
        else:
            raise PluginError("Invalid combo: " + fmt + ", " + bitSize)
    elif fmt == "G_IM_FMT_I":
        if bitSize == "G_IM_SIZ_4b":
            fImage.data = bytearray(
                [
                    int(
                        round(
                            colorToLuminance(
                                pixels[
                                    (j * image.size[0] + i) * image.channels : (j * image.size[0] + i) * image.channels
                                    + 3
                                ]
                            )
                            * 0xF
                        )
                    )
                    & 0xF
                    for j in reversed(range(image.size[1]))
                    for i in range(image.size[0])
                ]
            )
        elif bitSize == "G_IM_SIZ_8b":
            fImage.data = bytearray(
                [
                    int(
                        round(
                            colorToLuminance(
                                pixels[
                                    (j * image.size[0] + i) * image.channels : (j * image.size[0] + i) * image.channels
                                    + 3
                                ]
                            )
                            * 0xFF
                        )
                    )
                    & 0xFF
                    for j in reversed(range(image.size[1]))
                    for i in range(image.size[0])
                ]
            )
        else:
            raise PluginError("Invalid combo: " + fmt + ", " + bitSize)
    else:
        raise PluginError("Invalid image format " + fmt)

    # We stored 4bit values in byte arrays, now to convert
    if bitSize == "G_IM_SIZ_4b":
        fImage.data = compactNibbleArray(fImage.data, image.size[0], image.size[1])

    fImage.converted = True
