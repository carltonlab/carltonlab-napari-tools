from typing import TYPE_CHECKING

from napari.layers import Image

if TYPE_CHECKING:
    from napari.layers import Image
    from napari.viewer import ViewerModel


def _open_image_as_layer(
    napari_viewer: "ViewerModel", image_path: str
) -> "Image | None":
    opened_layer = napari_viewer.open(image_path)
    if isinstance(opened_layer[0], Image):
        return opened_layer[0]
    return None
