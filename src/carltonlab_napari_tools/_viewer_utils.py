from typing import cast

from napari.layers import Image
from napari.utils.notifications import show_info
from napari.viewer import ViewerModel

from carltonlab_napari_tools._shared_widgets import confirm_dialog


def close_image_layers(
    napari_viewer: ViewerModel,
    image_layers: list[Image],
) -> None:
    for image_layer in image_layers:
        if image_layer in napari_viewer.layers:
            napari_viewer.layers.remove(image_layer)


def validate_closed_layers(napari_viewer: ViewerModel) -> bool:
    if len(napari_viewer.layers) == 0:
        return True

    confirm_answer = confirm_dialog(
        napari_viewer,
        "All layers must be closed to open a new image. Proceed?",
        no_mode=True,
    )
    if not confirm_answer:
        return False

    napari_viewer.layers.clear()
    return True


def open_ome_zarr_layers(
    napari_viewer: ViewerModel,
    image_path: str,
) -> list[Image] | None:
    opened_layers = napari_viewer.open(image_path)

    if not isinstance(opened_layers, list):
        opened_layers = [opened_layers]

    opened_images = [
        layer for layer in opened_layers if isinstance(layer, Image)
    ]

    if not opened_images:
        show_info(
            f"No image layers were opened from the OME-Zarr path: "
            f"{image_path}"
        )
        return None

    if len(opened_images) == 1:
        image_layer = opened_images[0]
        image_data = image_layer.data

        if hasattr(image_data, "ndim") and image_data.ndim >= 4:
            close_image_layers(napari_viewer, [image_layer])

            split_layers = napari_viewer.add_image(
                image_data,
                channel_axis=1,
            )

            if isinstance(split_layers, Image):
                show_info(
                    "The OME-Zarr image could not be split into channels."
                )
                return None

            return cast(list[Image], split_layers)

    return opened_images
