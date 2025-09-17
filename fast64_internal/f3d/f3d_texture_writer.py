from itertools import combinations
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
from .texture_algorithms import (
    flatten_pixels,
    generate_ihq,
    generate_palette_kmeans,
    get_rgba_colors_float,
    color_to_luminance_np,
    check_if_greyscale,
    get_bit_depth_entropy,
    shrink_box,
)

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


def getTextureNamesFromImage(image: bpy.types.Image, fmt: str, parent: Union[FModel, FTexRect]):
    return getTextureNamesFromBasename(getImageName(image), fmt, parent, False)


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
    pal_length: int,
) -> tuple[FPaletteKey, FImage]:
    texFmt = texProp.tex_format
    palFmt = texProp.ci_format
    palFormat = texFormatOf[palFmt]
    paletteKey = FPaletteKey(palFmt, images)

    if is_pal_reference:
        fPalette = FImage(texProp.pal_reference, None, None, 1, pal_length, None)
        return paletteKey, fPalette

    # If palette already loaded, return that data.
    fPalette = parent.getTextureAndHandleShared(paletteKey)
    if fPalette is not None:
        # print(f"Palette already exists")
        return paletteKey, fPalette

    paletteName, filename = getTextureNamesFromBasename(palBaseName, palFmt, parent, True)
    fPalette = FImage(paletteName, palFormat, "G_IM_SIZ_16b", 1, pal_length, filename)

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


class AutoFormatInfo(NamedTuple):
    color_depth: int
    alpha_depth: int


RGBA_FORMAT_PROPS = {
    "RGBA32": AutoFormatInfo(8, 8),
    "RGBA16": AutoFormatInfo(5, 1),
}
IA_FORMAT_PROPS = {
    "IA16": AutoFormatInfo(8, 8),
    "IA8": AutoFormatInfo(4, 4),
    "IA4": AutoFormatInfo(4, 4),
}
I_FORMAT_PROPS = {
    "I8": AutoFormatInfo(8, 0),
    "I4": AutoFormatInfo(4, 0),
}
CI_FORMAT_PROPS = {
    "CI8": AutoFormatInfo(8, 1),
    "CI4": AutoFormatInfo(4, 1),
}


@dataclass
class TexInfo:
    load_tex: bool = False
    tex_reference: Optional[str] = None
    fmt: str | None = None
    _auto_fmt: bool = False
    main_image: Optional[FloatPixelsImage] = None
    _imDependencies: set[FloatPixelsImage] = field(default_factory=set)
    imageDims: tuple[int, int] = (0, 0)

    load_pal: bool = False
    pal_reference: Optional[str] = None
    pal_fmt: str = ""
    main_pal: Optional[FloatPixelsImage] = None
    _palDependencies: set[FloatPixelsImage] = field(default_factory=set)

    pal_length: int = -1

    mirror: tuple[bool, bool] = (False, False)
    clamp: tuple[bool, bool] = (False, False)
    shift: tuple[int, int] = (0, 0)
    low: tuple[float, float] = (0.0, 0.0)
    repeats: tuple[int, int] = (1, 1)
    auto_other_props: bool = False
    high: tuple[float, float] = (0.0, 0.0)
    mask: tuple[int, int] = (0, 0)

    # Auto format values
    alpha_depth_entropies: Optional[tuple[dict[int, float], float]] = field(default_factory=dict)
    color_depth_entropies: Optional[tuple[dict[int, float], float]] = field(default_factory=dict)
    is_greyscale: bool = False

    # Parameters computed by MultitexManager.writeAll
    texAddr: int = 0
    palAddr: int = 0
    pal_index: int = 0
    palBaseName: str = ""
    doTexTile: bool = True

    # Internal parameters--copies of passed parameters
    indexInMat: int = -1

    @property
    def has_tex(self) -> bool:
        return self.load_tex and self.tex_reference is None

    @property
    def auto_fmt(self) -> bool:
        return self._auto_fmt and self.has_tex

    @property
    def is_ci(self) -> bool:
        return self.fmt and self.fmt.startswith("CI")

    @property
    def tlut_mode(self) -> bool:
        return self.pal_fmt if self.is_ci else "NONE"

    @property
    def is_ia(self) -> bool:
        return self.fmt and self.fmt.startswith("I")

    @property
    def has_pal(self) -> bool:
        return self.is_ci and self.load_pal and self.pal_reference is None

    @property
    def pixel_count(self):
        return self.imageDims[0] * self.imageDims[1]

    @property
    def tmem_size(self) -> int:
        if self.fmt:
            return getTmemWordUsage(self.fmt, self.imageDims[0], self.imageDims[1])
        return -1

    @property
    def tmem_hash(self):
        values = [self.tex_reference, self.tmem_size, self.fmt]
        if self.tex_reference is None:
            if self.main_image is not None:
                values.append(self.main_image.name)
        values.append(self.imageDims)
        return hash(tuple(values))

    @property
    def recommended_color_bits(self):
        return max(self.color_depth_entropies[0].keys(), default=0)

    @property
    def recommended_alpha_bits(self):
        return max(self.alpha_depth_entropies[0].keys(), default=0)

    @property
    def palDependencies(self):
        return {self.main_pal} if self.main_pal is not None else self._palDependencies

    @property
    def imDependencies(self):
        return {self.main_image} if self.main_image is not None else self._imDependencies

    def get_fmts_with_penalty(self, is_ci: bool):
        if is_ci:
            info = CI_FORMAT_PROPS
        else:
            info = RGBA_FORMAT_PROPS
            if self.is_greyscale:
                info = IA_FORMAT_PROPS
                if self.recommended_alpha_bits == 0:
                    info = I_FORMAT_PROPS

        best_col = self.color_depth_entropies[1]
        best_alpha = self.alpha_depth_entropies[1]

        def pick_eff(ent_dict, bits):
            if not ent_dict:
                return 0
            for bit, eff in ent_dict.items():
                if bit >= bits:
                    return eff
            return ent_dict[max(ent_dict.keys())]

        fmt_penalties = {}
        for fmt, props in info.items():
            col_eff = pick_eff(self.color_depth_entropies[0], props.color_depth)
            alpha_eff = pick_eff(self.alpha_depth_entropies[0], props.alpha_depth)

            col_penalty = max(best_col - col_eff, 0)
            alpha_penalty = max(best_alpha - alpha_eff, 0)

            fmt_penalties[fmt] = col_penalty + alpha_penalty

        return fmt_penalties

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
        self.indexInMat = index

        self.mirror = (tex_prop.S.mirror, tex_prop.T.mirror)
        self.clamp = (tex_prop.S.clamp, tex_prop.T.clamp)
        self.shift = (tex_prop.S.shift, tex_prop.T.shift)
        self.low = (tex_prop.S.low, tex_prop.T.low)
        self.repeats = (tex_prop.S.repeats, tex_prop.T.repeats)
        self.auto_other_props = tex_prop.autoprop
        if self.auto_other_props:
            self.high = (tex_prop.S.high, tex_prop.T.high)
            self.mask = (tex_prop.S.mask, tex_prop.T.mask)

        if not pseudo_fmt:
            self.fmt = tex_prop.tex_format
            self.pal_fmt = tex_prop.ci_format if self.is_ci else ""
            self._auto_fmt = tex_prop.auto_fmt
        self.load_tex = tex_prop.load_tex or base_texture
        self.tex_reference = tex_prop.tex_reference if (tex_prop.use_tex_reference and not base_texture) else None
        img_deps = fModel.gather_images(material, tex_prop, self.tex_reference is not None, base_texture)
        # TODO: find way to skip gather pixels if we don´t need it? with caching it is the slowest operation by far
        # (with caching ihq, kmeans, etc are all a one time cost)
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
            else:
                if self.pal_reference is None:
                    self.pal_index = tex_prop.pal_index
                else:
                    self.pal_length = tex_prop.pal_reference_size

        self.values_from_dims(*tex_prop.size)

        return self

    def values_from_dims(self, width: int, height: int):
        self.imageDims = (width, height)
        if self.auto_other_props:
            high_mask = [[0, 0], [0, 0]]
            for i in range(2):
                high_mask[i] = calculate_high_mask(self.clamp[i], self.repeats[i], self.low[i], height)
            self.high = (high_mask[0][1], high_mask[1][1])
            self.mask = (high_mask[0][0], high_mask[1][0])
        if self.fmt == "YUV16":
            self.imageDims = (width, height * 2)

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
                self.pal_length,
            )

        # Write loads
        loadGfx = fMaterial.texture_DL
        f3d = fModel.f3d
        if self.load_pal:
            savePaletteLoad(loadGfx, fPalette, self.pal_fmt, self.palAddr, self.pal_length, 5 - self.indexInMat, f3d)
        if self.load_tex:
            saveTextureLoadOnly(fImage, loadGfx, self.texProp, None, 7 - self.indexInMat, self.texAddr, f3d)
        if self.doTexTile:
            saveTextureTile(
                fImage, fMaterial, loadGfx, self.texProp, None, self.indexInMat, self.texAddr, self.pal_index, f3d
            )

        # Write texture data
        if convertTextureData:
            if self.load_pal and not self.is_pal_reference:
                writePaletteData(fPalette, self.pal)
            if self.is_tex_reference:
                if self.is_ci:
                    fModel.writeTexRefCITextures(
                        self.flipbook, fMaterial, self.imDependencies, self.pal, self.fmt, self.pal_fmt
                    )
                else:
                    fModel.writeTexRefNonCITextures(self.flipbook, self.fmt)
            else:
                if self.is_ci:
                    assert (
                        self.pal is not None
                    ), "self.pal is None, either moreSetupFromModel or materialless_setup must be called beforehand"
                    writeCITextureData(self.texProp.tex, fImage, self.pal, self.pal_fmt, self.fmt)
                else:
                    writeNonCITextureData(self.texProp.tex, fImage, self.fmt)


MAX_IMAGES = 8


def get_fmt_size(fmt: str):
    return texBitSizeF3D[fmt]


GLOBAL_ENTROPY_CACHE = {}


@dataclass
class MultitexManager:
    textures: dict[int, TexInfo] = field(default_factory=dict)
    dithering_method: DITHER_MODES = "FLOYD"
    tex_dimensions: tuple[int, int] = (0, 0)

    @property
    def mip_levels(self):
        return max((i for i in self.textures.keys()), default=-1) + 1

    @property
    def auto_textures(self):
        return [tex for tex in self.textures.values() if tex.auto_fmt]

    @property
    def non_auto_textures(self):
        return [tex for tex in self.textures.values() if not tex.auto_fmt]

    @property
    def is_ci(self):
        cis = [tex.is_ci for tex in self.non_auto_textures]
        return any(cis) if cis else None

    @property
    def max_tmem_size(self):
        return 256 if self.is_ci else 256 * 2

    @property
    def tlut_mode(self):
        modes = list(set(tex.tlut_mode for tex in self.texture_list))
        if modes:
            return modes[0]
        return None

    @property
    def texture_list(self):
        return list(self.textures.values())

    def calculate_tmem_allocations(self, texture_list=None):
        """
        Calculate which textures will fill each space in TMEM, this will be used to calculate usage and addresses
        """

        class TexAlloc(NamedTuple):
            start: int
            end: int
            tex_hash: int
            lower: bool

            def __str__(self):
                return f"({self.start}, {self.end}): ({self.tex_hash} - {self.lower})"

            def __repr__(self):
                return str(self)

        if texture_list is None:
            texture_list = self.texture_list
        textures = sorted(texture_list, key=lambda tex: tex.tmem_size and tex.fmt not in {"RGBA32"})
        allocations: list[TexAlloc] = []  # (start, end, tex, lower)

        for tex in textures:
            if tex.fmt == "RGBA32":
                half_size = tex.tmem_size // 2
                new_allocations = [(half_size, tex.tmem_hash, False), (half_size, tex.tmem_hash, True)]
            else:
                new_allocations = [(tex.tmem_size, tex.tmem_hash, False)]

            for tmem_size, tmem_hash, lower in new_allocations:
                if tmem_size == -1:
                    continue
                if any(other_hash == tmem_hash and l == lower for _, _, other_hash, l in allocations):
                    continue  # check if already present

                for i in range(len(allocations) - 1):
                    gap_start = allocations[i][1]
                    gap_end = allocations[i + 1][0]
                    gap_size = gap_end - gap_start

                    if (gap_start <= self.max_tmem_size // 2) == lower:
                        continue

                    if gap_size >= tmem_size:  # fits in this gap
                        allocations.append(TexAlloc(gap_start, gap_start + tmem_size, tmem_hash, lower))
                        allocations.sort(key=lambda x: x[0])  # ensure sorted
                        break
                else:  # place at the end
                    starting_end = self.max_tmem_size // 2 if lower == True else 0
                    last_end = max((end for _, end, *_ in allocations if end > starting_end), default=starting_end)
                    allocations.append(TexAlloc(last_end, last_end + tmem_size, tmem_hash, lower))
                    allocations.sort(key=lambda x: x[1])  # ensure sorted

        return allocations

    def get_tmem_size(self):
        return sum(end - start for start, end, *_ in self.calculate_tmem_allocations())

    def get_free_tmem_spaces(self, allocs=None):
        if allocs is None:
            allocs = self.calculate_tmem_allocations()
        free_spaces = []
        for i in range(len(allocs) - 1):
            start = allocs[i][1]
            end = allocs[i + 1][0]
            if end - start > 0:
                free_spaces.append((start, end))
        return free_spaces

    def get_available_tmem(self, allocs=None):
        if allocs is None:
            allocs = self.calculate_tmem_allocations()
        end = max((end for _, end, *_ in allocs), default=0)
        if end > self.max_tmem_size:
            return -1
        else:
            remaining_tmem = self.max_tmem_size - end
            biggest_gap = max(
                (end - start for start, end in self.get_free_tmem_spaces(allocs) if end <= self.max_tmem_size),
                default=-1,
            )
            return max(remaining_tmem, biggest_gap)

    def __repr__(self):
        return (
            f"MultitexManager(\n\ttlut_mode={self.tlut_mode}, \n"
            f"\ttotal_tmem={self.get_tmem_size()}/{self.max_tmem_size}, available_tmem={self.get_available_tmem()}, "
            f"free_spaces={self.get_free_tmem_spaces()},\n"
            f"\tallocations={self.calculate_tmem_allocations()}, \n"
            f"\ttextures={self.textures}, \n\tdithering_method={self.dithering_method}, \n\tmip_levels={self.mip_levels}\n)"
        )

    def generate_mip(
        self, base: TexInfo, mips: int, i: int, ignore_restrictions: bool = False, img: FloatPixelsImage | None = None
    ):
        divisor = (mips + 1) * 2
        width, height = base.imageDims
        n_width, n_height = width // divisor, height // divisor
        if (n_width < 4) or (n_height < 4):
            return False

        new = base.copy()
        new.values_from_dims(n_width, n_height)
        # create tmem allocations and see if tmem exceeds n64 boundaries (-1)
        if (
            not ignore_restrictions
            and self.get_available_tmem(self.calculate_tmem_allocations(self.texture_list + [new])) < 0
        ):
            return False

        if img is None:
            img = base.main_image
        new.main_image = FloatPixelsImage(img.name + f"_mip{mips}", shrink_box(img, divisor, divisor))
        # print(n_width, n_height, new.main_image.pixels)
        if img == base.main_pal:
            new.main_pal = new.main_image
        new.indexInMat = i
        self.textures[i] = new
        return True

    def generate_mipmaps(self, ignore_restrictions: bool = False):
        prev, mips = None, 0
        for i in range(MAX_IMAGES):
            if i in self.textures:
                prev, mips = self.textures[i], 0
                continue
            elif prev is None:
                continue
            assert prev.main_image is not None, "prev.main_image is None"
            if not self.generate_mip(prev, mips, i, ignore_restrictions):
                break
            mips += 1

    def generate_ihq(self, ignore_restrictions: bool = False):
        assert len(self.textures) == 1 and 0 in self.textures, "Only one (first) texture is supported for IHQ."
        base_tex = self.textures[0]
        i4_tex = base_tex.copy()
        rgba_tex = base_tex.copy()
        starting_img = base_tex.main_image

        intensity, rgba, uses_alpha = generate_ihq(starting_img)
        i4_tex.main_image = FloatPixelsImage(starting_img.name + "_ihq_i", intensity)
        i4_tex.fmt = "IA4" if uses_alpha else "I4"
        i4_tex.values_from_dims(intensity.shape[0], intensity.shape[1])
        self.textures[0] = i4_tex

        rgba_tex.main_image = FloatPixelsImage(starting_img.name + "_ihq_rgba", rgba)
        rgba_tex.fmt = "RGBA16"
        rgba_tex.shift = (rgba_tex.shift[0] + 1, rgba_tex.shift[1] + 1)
        if rgba_tex.shift[0] > 10 or rgba_tex.shift[1] > 10:
            raise PluginError("Shift is too large for IHQ.")
        rgba_tex.values_from_dims(rgba.shape[0], rgba.shape[1])
        rgba_tex.indexInMat = 1
        self.textures[1] = rgba_tex

        for mips in range(0, MAX_IMAGES - 2):
            if not self.generate_mip(rgba_tex, mips, mips + 2, ignore_restrictions, starting_img):
                break

    def from_mat(
        self,
        mat: bpy.types.Material,
        f_material: FMaterial,
        fModel: FModel,
        convert_texture_data: bool,
        ignore_restrictions: bool = False,
    ):
        f3d_mat: "F3DMaterialProperty" = mat.f3d_mat
        pseudo_format = f3d_mat.pseudo_format
        for i, tex_prop in f3d_mat.set_textures.items():
            tex = TexInfo()
            tex.from_prop(tex_prop, i, mat, fModel, False, False, pseudo_format != "NONE")
            self.textures[i] = tex

        uv_basis_index = f3d_mat.uv_basis_index
        if uv_basis_index in self.textures:
            main_tex = self.textures[uv_basis_index]
            self.tex_dimensions = main_tex.imageDims

        match pseudo_format:
            case "IHQ":
                self.generate_ihq(ignore_restrictions)
        self.figure_out_auto(ignore_restrictions)
        if pseudo_format == "NONE" and f3d_mat.gen_auto_mips:
            self.generate_mipmaps(ignore_restrictions)
        if convert_texture_data:
            self.convert()

    def figure_out_auto(self, ignore_restrictions=False):
        if not any(tex.auto_fmt for tex in self.texture_list):
            return
        if ignore_restrictions:
            for tex in self.texture_list:
                tex.fmt = "RGBA32"
            return

        texture_list = sorted(self.texture_list, key=lambda tex: tex.pixel_count)
        auto_textures = [tex for tex in texture_list if tex.auto_fmt]

        for tex in auto_textures:  # figure out important properties
            if not tex.auto_fmt:
                continue
            if tex.main_image.pixel_hash in GLOBAL_ENTROPY_CACHE:
                tex.is_greyscale, tex.alpha_depth_entropies, tex.color_depth_entropies = GLOBAL_ENTROPY_CACHE[
                    tex.main_image.pixel_hash
                ]
                continue
            flat_pixels = flatten_pixels(tex.main_image.pixels)
            tex.is_greyscale = check_if_greyscale(flat_pixels)
            tex.alpha_depth_entropies = get_bit_depth_entropy(flat_pixels[..., 3])
            if tex.is_greyscale:
                tex.color_depth_entropies = get_bit_depth_entropy(color_to_luminance_np(flat_pixels))
            else:
                tex.color_depth_entropies = get_bit_depth_entropy(flat_pixels[..., :3])
            GLOBAL_ENTROPY_CACHE[tex.main_image.pixel_hash] = (
                tex.is_greyscale,
                tex.alpha_depth_entropies,
                tex.color_depth_entropies,
            )

        tlut_mode = self.tlut_mode
        if tlut_mode is None:  # tlut not defined (no non auto textures). figure out if we should use ci mode
            tlut_mode = "NONE"
            sizes = sum(tex.pixel_count for tex in self.texture_list)
            any_is_greyscale = any(tex.is_greyscale for tex in self.texture_list)
            tex_count = len(self.texture_list)
            if tex_count > 0:
                average_hor = sum(tex.imageDims[0] for tex in self.texture_list) // tex_count
                average_color_entropy = sum(tex.color_depth_entropies[1] for tex in self.texture_list) / tex_count
                significant_alpha = any(tex.recommended_alpha_bits > 2 for tex in self.texture_list)
                if (
                    not significant_alpha
                    and (not any_is_greyscale and (average_hor >= 16) and average_color_entropy <= 3)
                ) or ((sizes > 32 * 64 and sizes <= 64 * 64) and not any_is_greyscale):
                    tlut_mode = "RGBA16"
        use_ci = tlut_mode != "NONE"

        for tex in auto_textures:  # assign initial recommended texture format
            fmt_penalties = tex.get_fmts_with_penalty(use_ci)
            tex.fmt = min(fmt_penalties.keys(), key=lambda fmt: fmt_penalties[fmt])
            if use_ci:
                tex.pal_fmt = "RGBA16"

        while self.get_available_tmem() < 0:  # keep downgrading until texxtures fit in tmem
            best_choice = None
            smallest_penalty_increase = math.inf

            for tex in auto_textures:
                fmt_penalties = tex.get_fmts_with_penalty(use_ci)

                current_penalty = fmt_penalties[tex.fmt]
                next_penalty, next_fmt = math.inf, None

                for fmt, penalty in fmt_penalties.items():
                    if fmt != tex.fmt and penalty > current_penalty:
                        next_penalty, next_fmt = penalty, fmt
                if next_fmt is None:
                    continue  # can't downgrade further

                penalty_increase = next_penalty - current_penalty
                best_fmt = next_fmt

                if penalty_increase < smallest_penalty_increase:
                    smallest_penalty_increase = penalty_increase
                    best_choice = (tex, best_fmt)

            if best_choice is None:  # if can´t downgrade more, break
                break
            else:  # downgrade the texture with smallest penalty increase
                tex, fmt = best_choice
                tex.fmt = fmt

    def find_optimal_ci4_merges(
        self, ci4_to_merge: list, rgba_palettes: dict[int, tuple[FloatPixels, FlatPixels]], remaining_colors: int
    ):
        TEXTURE_ID = frozenset[FloatPixelsImage, ...]
        failed_combinations: set[TEXTURE_ID] = set()
        merge_results: dict[TEXTURE_ID, tuple[np.ndarray, np.ndarray, float, dict]] = {}

        for tex in ci4_to_merge:
            tex_id: TEXTURE_ID = frozenset(tex.palDependencies)

            palette_pixels = [rgba_palettes[pal.pixel_hash][1] for pal in tex.palDependencies]
            joined_pixels = np.vstack(palette_pixels)
            pal, labels, inertia = generate_palette_kmeans(joined_pixels, min(16, remaining_colors))
            num_pixels = len(joined_pixels)
            rmse = np.sqrt(inertia / num_pixels) if num_pixels > 0 else 0
            slice_map = {tex_id: slice(0, num_pixels)}

            merge_results[tex_id] = (pal, labels, rmse, slice_map)

        # try to merge ci4's together, 2 at a time, then 3 at a time, etc
        # skip bad combinations
        for r in range(2, len(ci4_to_merge) + 1):
            for texture_group in combinations(ci4_to_merge, r):
                current_ids_list: list[TEXTURE_ID] = [frozenset(t.palDependencies) for t in texture_group]
                group_id: TEXTURE_ID = frozenset.union(*current_ids_list)

                # this combo is already known to be bad
                if any(frozenset(failed).issubset(group_id) for failed in failed_combinations):
                    continue

                pixel_data_map = {
                    tid: np.vstack([rgba_palettes[p.pixel_hash][1] for p in tid]) for tid in current_ids_list
                }
                all_pixels_to_join = []
                slice_map = {}
                current_offset = 0
                for tid, pixels in pixel_data_map.items():
                    all_pixels_to_join.append(pixels)
                    slice_map[tid] = slice(current_offset, current_offset + len(pixels))
                    current_offset += len(pixels)

                joined_pixels = np.vstack(all_pixels_to_join)
                pal, labels, inertia = generate_palette_kmeans(joined_pixels, min(16, remaining_colors))
                num_pixels_total = len(joined_pixels)
                merged_rmse = np.sqrt(inertia / num_pixels_total) if num_pixels_total > 0 else 0

                # get the smallest individual error from the textures in this group
                max_individual_rmse = min(
                    merge_results.get(tid, (None, None, float("inf"), None))[2] for tid in current_ids_list
                )

                if merged_rmse > max_individual_rmse:
                    failed_combinations.add(group_id)
                else:
                    merge_results[group_id] = (pal, labels, merged_rmse, slice_map)

        all_original_ids = {frozenset(t.palDependencies) for t in ci4_to_merge}
        assigned_ids = set()
        final_merges: dict[frozenset[FloatPixelsImage, ...], tuple[np.ndarray, np.ndarray, float, dict]] = {}

        sorted_merges = sorted(
            merge_results.items(),
            key=lambda item: len(item[1][3]),  # sort by biggest groups
            reverse=True,  # descending order
        )

        # assign non overlapping merges
        for group_id, result_tuple in sorted_merges:
            member_ids = set(result_tuple[3].keys())
            if assigned_ids.isdisjoint(member_ids):
                final_merges[group_id] = result_tuple
                assigned_ids.update(member_ids)
            if assigned_ids == all_original_ids:
                break

        return final_merges

    def create_pallete(self, ignore_restrictions=False):
        assert self.is_ci == True, "Can only create palette for CI textures"

        num_colors_used = 0
        for tex in self.texture_list:
            if tex.is_ci and not tex.load_pal and tex.pal_reference:
                num_colors_used += tex.pal_length

        remaining_colors = 256 - num_colors_used
        ci4_texs = [tex for tex in self.texture_list if tex.fmt == "CI4"]
        ci8_texs = [tex for tex in self.texture_list if tex.fmt == "CI8"]

        rgba_palettes = {}
        for tex in ci4_texs + ci8_texs:
            if tex.load_pal:
                palletes = tex.palDependencies
                for pallete in palletes:
                    if pallete.pixel_hash not in rgba_palettes:
                        rgba16 = get_rgba_colors_float(pallete.pixels)
                        rgba_palettes[pallete.pixel_hash] = rgba16, flatten_pixels(rgba16.round())

        ci4 = self.find_optimal_ci4_merges(
            [tex for tex in self.texture_list if tex.fmt == "CI4" and tex.load_pal], rgba_palettes, remaining_colors
        )
        pass

    def convert(self, ignore_restrictions=False):
        if self.is_ci:
            self.create_pallete(ignore_restrictions)

    def getTexDimensions(self):
        return self.tex_dimensions


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
# pal_length is the number of colors
def savePaletteLoad(
    gfxOut: GfxList,
    fPalette: FImage,
    palFormat: str,
    palAddr: int,
    pal_length: int,
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
            DPLoadTLUTCmd(loadtile, pal_length - 1),
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
