import hashlib
import math
from typing import Literal, Any
import numpy as np

from ..utility import RGB_TO_LUM_COEF
from .f3d_gbi import HEIGHT_T, WIDTH_T, FlatPixels, FloatPixels, N64Pixels, FloatPixelsImage


GLOBAL_SHRINK_BOX_CACHE: dict[tuple[str, int, int], FloatPixels] = {}


def shrink_box(img: FloatPixels, width_div: int, height_div: int):
    if (img.pixel_hash, width_div, height_div) in GLOBAL_SHRINK_BOX_CACHE:
        return GLOBAL_SHRINK_BOX_CACHE[(img.pixel_hash, width_div, height_div)]
    assert width_div > 1 and height_div > 1
    pixels = img.pixels
    height, width, channels = pixels.shape

    n_width = math.ceil(width / width_div)
    n_height = math.ceil(height / height_div)

    pad_width = n_width * width_div - width
    pad_height = n_height * height_div - height

    # pad if needed
    if pad_width > 0 or pad_height > 0:
        pixels = np.pad(pixels, ((0, pad_height), (0, pad_width), (0, 0)), mode="edge")  # repeat edge pixels

    pixels = pixels.reshape(n_height, height_div, n_width, width_div, channels).mean(axis=(1, 3))

    GLOBAL_SHRINK_BOX_CACHE[(img.pixel_hash, width_div, height_div)] = pixels
    return pixels


def flatten_pixels(pixels: FloatPixels) -> FlatPixels:
    return pixels.reshape((np.prod(pixels.shape[:-1]), pixels.shape[-1]))


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
    pixels: np.ndarray[np.float32, (Any, Any, Any)], target_size: tuple[int, int]
) -> np.ndarray[np.float32, (WIDTH_T, HEIGHT_T, Any)]:
    old_height, old_width, _ = pixels.shape
    target_width, target_height = target_size

    j, i = np.meshgrid(np.arange(target_height), np.arange(target_width), indexing="ij")

    # source coordinates
    y_ratio = (old_height - 1) / max(target_height - 1, 1)
    x_ratio = (old_width - 1) / max(target_width - 1, 1)
    y_old = j * y_ratio
    x_old = i * x_ratio

    # integer coordinates
    y0 = np.floor(y_old).astype(np.int32)
    x0 = np.floor(x_old).astype(np.int32)
    y1 = np.minimum(y0 + 1, old_height - 1)
    x1 = np.minimum(x0 + 1, old_width - 1)

    p00 = pixels[y0, x0]  # top-left
    p10 = pixels[y1, x0]  # bottom-left
    p01 = pixels[y0, x1]  # top-right
    p11 = pixels[y1, x1]  # bottom-right

    # fractions
    dy = y_old - y0
    dx = x_old - x0
    dy = dy[:, :, np.newaxis]
    dx = dx[:, :, np.newaxis]

    # bilinear interpolation
    interpolated = p00 * (1 - dx) * (1 - dy) + p01 * dx * (1 - dy) + p10 * (1 - dx) * dy + p11 * dx * dy

    return interpolated


GLOBAL_IHQ_CACHE: dict[str, tuple] = {}


def generate_ihq(img: FloatPixelsImage):
    if img.pixel_hash in GLOBAL_IHQ_CACHE:
        return GLOBAL_IHQ_CACHE[img.pixel_hash]

    pixels = img.pixels
    height, width, _ = pixels.shape

    alpha_channel = pixels[:, :, 3]
    color_channels = pixels[:, :, :3]
    uses_alpha = np.any(alpha_channel < 0.5)
    yuv_target = color_channels.reshape(-1, 3) @ YUV_MATRIX.T

    best_err = np.inf
    best_i_pixels, best_rgba_pixels = None, None
    for dir in range(2):
        width_div, height_div = 4, 2
        if dir == 0 and width % 4 == 0:
            width_div, height_div = 4, 2
        elif dir == 1 and height % 4 == 0:
            width_div, height_div = 2, 4
        down_scale = shrink_box(img, width_div=width_div, height_div=height_div)
        bilinear_upscale = bilinear_resize(down_scale[:, :, :3], target_size=(width, height))
        yuv_base = bilinear_upscale.reshape(-1, 3) @ YUV_MATRIX.T
        for ifactor in range(1, 11):
            ifactor *= 0.05
            i_pixels, error = ihq_calc_best_i(width, height, yuv_base, yuv_target, ifactor)

            if error < best_err:
                best_err = error
                best_i_pixels, best_rgba_pixels = i_pixels, down_scale

    if uses_alpha:
        best_i_pixels = np.stack([best_i_pixels, best_i_pixels, best_i_pixels, alpha_channel], axis=2)  # to rgb
    else:
        best_i_pixels = np.stack([best_i_pixels, best_i_pixels, best_i_pixels], axis=2)

    GLOBAL_IHQ_CACHE[img.pixel_hash] = best_i_pixels, best_rgba_pixels, uses_alpha
    return best_i_pixels, best_rgba_pixels, uses_alpha


def kmeans_plusplus(pixels: FlatPixels, n_colors: int):
    """Fancier way to initialize kmeans, basically insures initial centroids are already decent"""
    pixel_count = pixels.shape[0]
    np.random.seed(pixel_count * n_colors)  # make deterministic
    centroids = np.empty_like(pixels, shape=(n_colors, pixels.shape[1]))

    centroids[0] = pixels[np.random.randint(pixel_count)]

    closest_dist_sq = np.full(pixel_count, np.inf)

    for i in range(1, n_colors):
        # squared distance of previous centroid
        dist_sq = np.sum((pixels - centroids[i - 1]) ** 2, axis=1)
        closest_dist_sq = np.minimum(closest_dist_sq, dist_sq)

        # Choose the next centroid with probability proportional to D(x)^2
        # This is a weighted random choice based on the squared distances
        dist_sum = np.sum(closest_dist_sq)
        if dist_sum == 0:  # for example, a solid color image
            probabilities = np.full(pixel_count, 1 / pixel_count)
        else:
            probabilities = closest_dist_sq / dist_sum
        centroids[i] = pixels[np.random.choice(pixel_count, p=probabilities)]

    return centroids


def generate_palette_kmeans(pixels_flat: FlatPixels, n_colors: int, max_iter: int = 32, tolerance: float = 1 / 255):
    """Quantize pallete using kmeans++. Returns pallete, texture and error"""
    assert n_colors >= 1, "n_colors < 1"
    assert tolerance >= 0, "tolerance < 0"
    assert n_colors <= 255 or n_colors < 0, "n_colors > 255 or n_colors < 0"

    unique_colors, inverse_indices = np.unique(pixels_flat, axis=0, return_inverse=True)
    if len(unique_colors) <= n_colors:
        return unique_colors, inverse_indices, 0

    centroids = kmeans_plusplus(pixels_flat, n_colors)

    converged = False
    for _ in range(max_iter):
        distances = np.linalg.norm(pixels_flat[:, np.newaxis] - centroids, axis=-1)
        labels: np.ndarray[np.uint8, n_colors] = np.argmin(distances, axis=-1)  # closest centroid

        new_centroids = np.empty_like(centroids)
        for i in range(n_colors):
            cluster_pixels = pixels_flat[labels == i]
            if cluster_pixels.size > 0:
                new_centroids[i] = cluster_pixels.mean(axis=0)
            else:
                new_centroids[i] = centroids[i]

        if np.linalg.norm(new_centroids - centroids) < 1e-4:  # check for convergence
            converged = True
        centroids = new_centroids
        if converged:
            break

    return centroids, labels, math.sqrt(np.sum(np.square(pixels_flat - centroids[labels])))


def compact_nibble_np(pixels: N64Pixels[np.uint8]) -> N64Pixels[np.uint8]:
    if len(pixels) % 2 != 0:  # uneven pixel count. this is uncommon, don't bother with a more opt approach
        pixels = np.append(pixels, pixels[-1])
    return (pixels[::2] << 4) | pixels[1::2]


def get_best_np_type(size: int):
    size = max(8, size)
    assert hasattr(np, f"uint{size}"), f"Invalid size {size}"
    return getattr(np, f"uint{size}")


# Conversion functions


RGBA_SCALE = lambda r, g, b, a: np.array((2**r - 1, 2**g - 1, 2**b - 1, 2**a - 1))


def get_rgba_colors_float(pixels: FloatPixels, r=5, g=5, b=5, a=1) -> np.ndarray[float, (Any, Any, 4)]:
    return pixels * RGBA_SCALE(r, g, b, a)


def rounded_rgba_to_n64(
    rounded_pixels: np.ndarray[float, (Any, Any, 4)], r=5, g=5, b=5, a=1
) -> N64Pixels[np.uint16 | np.uint32]:
    pixels = rounded_pixels.astype(get_best_np_type(r + g + b + a))
    return pixels[:, 0] << (g + b + a) | pixels[:, 1] << (b + a) | pixels[:, 2] << a | pixels[:, 3]


def get_a3rgb5_colors_float(pixels: FloatPixels) -> np.ndarray[float, (Any, Any, 4)]:
    """Doesn´t return in correct order, as it would be a waste of time.
    That's handled in rounded_a3rgb5_to_n64.
    Each pixel can either be 5 bit RGB (opaque) or 4 bit RGB 3 bit alpha.
    The upper 16th bit defines if a pixel is fully opaque,
    therefor ignoring the other 3 bits that would otherwise be used for alpha.
    """
    a3rgb5 = pixels * np.array((2**5 - 1, 2**5 - 1, 2**5 - 1, 2**3 - 1))
    a3rgb4 = pixels * np.array((2**4 - 1, 2**4 - 1, 2**4 - 1, 1))
    return np.where(pixels[:, 3] == 1.0, a3rgb5, a3rgb4)


def rounded_a3rgb5_to_n64(rounded_pixels: np.ndarray[float, (Any, Any, 4)]) -> N64Pixels[np.uint16]:
    rounded_pixels = rounded_pixels.astype(get_best_np_type(16))
    opaque_mask = rounded_pixels[:, 3] == 2**3 - 1
    opaque_pixels = 1 << 15 | rounded_pixels[:, 0] << 10 | rounded_pixels[:, 1] << 5 | rounded_pixels[:, 2]
    translucent_pixels = (
        rounded_pixels[:, 3] | rounded_pixels[:, 0] << 8 | rounded_pixels[:, 1] << 4 | rounded_pixels[:, 2]
    )
    return np.where(opaque_mask, opaque_pixels, translucent_pixels)


def color_to_luminance_np(pixels: FloatPixels) -> FloatPixels:
    return np.dot(pixels[..., :3], RGB_TO_LUM_COEF)


def get_ia_colors_float(pixels: FloatPixels, i=8, a=8) -> np.ndarray[float, (Any, Any, Literal[1, 2])]:
    lum = color_to_luminance_np(pixels) * (2**i - 1)
    if a > 0:
        alpha_pixels = pixels[..., 3] * (2**a - 1)
        return np.stack((lum, alpha_pixels), axis=-1)
    return lum.reshape((*pixels.shape[:-1], 1))


def rounded_ia_to_n64(
    rounded_pixels: np.ndarray[float, (Any, Any, Literal[1, 2])], i=8, a=8
) -> FlatPixels[np.uint8 | np.uint16]:
    typ = get_best_np_type(i + a)
    result = rounded_pixels.astype(typ)
    if a > 0:
        result = result[:, 0] << a | result[:, 1]
    if i + a == 4:
        return compact_nibble_np(result)
    return result


def check_if_greyscale(pixels: FloatPixels, threshold: int = 1 / 255) -> bool:
    alpha = pixels[..., 3]
    mask = alpha >= 1 / 255

    selected = pixels[..., :3][mask]
    if selected.size == 0:  # no opaque pixels to check
        return True

    diffs = selected.max(axis=1) - selected.min(axis=1)
    return np.all(diffs <= threshold)


def get_bit_depth_entropy(image: FloatPixels, efficiency_threshold: float = 0.6):
    """
    Figure out a resonable bit depth by calculating its entropy change in a quantized step.
    (by selling your soul to the devil)
    This returns a dict of bit depths as the key, highest being recommended, with their entropies as the values.
    And the original entropy as the second value.
    """

    def calculate_quantized_entropy(target_bits: int) -> float:
        levels = 2**target_bits
        quantized_image = np.round(image * (levels - 1)).astype(np.uint8)
        hist = np.histogram(quantized_image, bins=levels, range=(0, levels))[0]

        total_pixels = hist.sum()
        if total_pixels == 0:
            return 0.0

        probs = hist / total_pixels
        nonzero_probs = probs[probs > 0]

        # Shannon entropy formula
        return -np.sum(nonzero_probs * np.log2(nonzero_probs))

    if image.size == 0:
        return 0, 0

    original_entropy = calculate_quantized_entropy(8)

    if original_entropy < 0.1:
        return {}, original_entropy

    entropies = {}
    for bits in [1, 2, 4, 5]:
        quantized_entropy = calculate_quantized_entropy(bits)

        efficiency = quantized_entropy / original_entropy
        entropies[bits] = quantized_entropy
        if efficiency >= efficiency_threshold:
            return entropies, original_entropy

    entropies[8] = original_entropy
    return entropies, original_entropy
