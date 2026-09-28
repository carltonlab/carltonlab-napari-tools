# carltonlab-napari-tools

[![License BSD-3](https://img.shields.io/github/license/carltonlab/carltonlab-napari-tools.svg?color=green)](https://github.com/carltonlab/carltonlab-napari-tools/blob/main/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![tests](https://github.com/carltonlab/carltonlab-napari-tools/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/carltonlab/carltonlab-napari-tools/actions/workflows/test_and_deploy.yml)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/carltonlab-napari-tools)](https://napari-hub.org/plugins/carltonlab-napari-tools)
[![npe2](https://img.shields.io/badge/plugin-npe2-blue?link=https://napari.org/stable/plugins/index.html)](https://napari.org/stable/plugins/index.html)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-purple.json)](https://github.com/copier-org/copier)

## About the plugin

Work in progress, please expect bugs V0.1.0

This napari plugin is a tool designed to computationally count the number of foci in microscopy of
_C. elegans_ gonads. It has two operational methods, manual and automatic counting. It uses
[ndevio](https://github.com/ndev-kit/ndevio) to extract the required metadata and
[multiview-stitcher](https://github.com/multiview-stitcher/multiview-stitcher) to stitch the gonad
tiles into a single image.

<p align="center">
  <img src="https://raw.githubusercontent.com/carltonlab/carltonlab-napari-tools/main/docs/images/stitched_image_example.png" alt="Example of a stitched gonad image">
</p>

The tool was designed for RAD-51 foci counting in 4D images (CZYX) since it is the most common assay
for quantification of DSBs in _C. elegans_ but can be used to count other foci in any image.

It features multi-gonad project creation where all genotypes and gonads are mixed after individual
nuclei are selected (manual or automatic) and are scored in a blind manner to minimize human bias.

We recommend using the automatic process, which uses a trained `cellpose` model to segment the
nuclei. By default, it uses our trained model:
<https://bioimage.io/#/artifacts/sneaky-panda>.

<p align="center">
  <img src="https://raw.githubusercontent.com/carltonlab/carltonlab-napari-tools/main/docs/images/meiotic_nuclei_segmentation_model_v1.png" alt="Example of meiotic nuclei segmentation">
</p>

For the automatic counting, it uses `spotiflow` with a default model and then point filtering
based on user provided parameters such as expected foci volume, channel (usually DAPI)
co-localization and more.

It'll export the data as plots that can be organized by genotype similar to the conventional RAD-51
scoring figures commonly used in papers.

<p align="center">
  <img src="https://raw.githubusercontent.com/carltonlab/carltonlab-napari-tools/main/docs/images/plot_example.svg" alt="Example of generated foci-counting plots">
</p>

It also writes all the intermediate files for troubleshooting, data archive and manual inspection.
Formats are `OME-Zarr` for tiles and stitched images, `TIFF` files for cropped nuclei, `CSV` files
for foci coordinates and feature tables. All which are easy to inspect even without the tool.

You can also do the entire counting and refinement of the data using the manual process.

## Installation

### Install from PyPI or napari Hub

Install the plugin in napari:

- In napari, open **Plugins → Install/Uninstall Plugins…**, search for
  `carltonlab-napari-tools`, select it, and click **Install**. Restart napari if
  prompted.
- If **Install/Uninstall Plugins…** isn't available, install the
  [napari plugin manager](https://napari.org/napari-plugin-manager/) in the
  same environment as napari.
- Or, in the Python environment used by napari, run:

  ```sh
  python -m pip install carltonlab-napari-tools
  ```

The commands above install the plugin's base dependencies. For automatic
segmentation, install the matching extra in the same Python environment:

For CPU:

```sh
python -m pip install "carltonlab-napari-tools[full-cpu]"
```

For CUDA 12:

```sh
python -m pip install "carltonlab-napari-tools[full-cuda12]"
```

Depending on your system, you may need a different PyTorch build for CUDA.

### Install from source

Clone the repository and enter its directory:

```sh
git clone git@github.com:carltonlab/carltonlab-napari-tools.git
cd carltonlab-napari-tools
```

Select what segmentation you'll be using (Automatic workflow only).

For the manual workflow, install napari and Qt without the segmentation
models:

```sh
uv sync --extra all
```

For automatic segmentation on CPU, use:

```sh
uv sync --extra full-cpu
```

For automatic segmentation with CUDA 12, use:

```sh
uv sync --extra full-cuda12
```

We highly recommend using a GPU for the segmentation. Depending on the setup, you might need to
install a different `PyTorch` version.

For our workflow, with approximately 2 × 50 × 1024 × 1024 (CZYX) images,
segmentation and foci counting use about 6 GB
of VRAM.

## Running

Launch napari from the environment where you installed the plugin:

- If you installed it through napari's plugin manager, pip, or conda, launch
  napari as you normally do.
- If you installed from source using uv, run this from the repository directory:

```sh
uv run napari
```

Then, use the Plugins menu to launch the tool.

## Contributing

Contributions are very welcome.

## Acknowledgements

This plugin uses [ndevio](https://github.com/ndev-kit/ndevio) for image metadata
and [multiview-stitcher](https://github.com/multiview-stitcher/multiview-stitcher)
for image stitching.

If you use `multiview-stitcher` in published research, cite its
[Zenodo record](https://doi.org/10.5281/zenodo.13151252).

## License

Distributed under the terms of the
[BSD-3](https://opensource.org/licenses/BSD-3-Clause) license,
"carltonlab-napari-tools" is free and open source software
