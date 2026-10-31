"""Thin setuptools wrapper; metadata lives in pyproject.toml."""

from setuptools import setup

with open("README-pypi.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pyrockimagelab",
    version="0.1.1",
    author="Larry Syu-Heng Lai",
    description="Browser app and tools for core and outcrop image processing, data collection, and automated geological and geomorphic classification and analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GeoLarryLai/pyRockImageLab",
    packages=["pyrockimagelab", "pyrockimagelab.common", "pyrockimagelab.image_processing", "pyrockimagelab.core_box", "pyrockimagelab.webapp", "pyrockimagelab.webapp.shell"],
    package_data={"pyrockimagelab.webapp": ["static/*", "shell/static/*"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.20",
        "opencv-python>=4.5",
        "Pillow>=8.3",
        "matplotlib>=3.5",
        "fastapi>=0.100",
        "uvicorn>=0.23",
        "pillow-heif>=0.13",
    ],
    entry_points={
        "console_scripts": [
            "pyrockimagelab=pyrockimagelab.core_box.processing:main",
            "pyrockimagelab-app=pyrockimagelab.webapp:main",
        ],
    },
    license="AGPL-3.0-or-later",
)
