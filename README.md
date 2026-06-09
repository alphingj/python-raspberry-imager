# Raspberry Pi Imager - Python Qt GUI

A Python-based GUI tool for flashing Raspberry Pi OS images to SD cards and USB drives using PyQt5.

## Features
- **OS Selection**: Browse official Raspberry Pi OS images with category filtering
- **Device Detection**: Auto-detect USB/SD card devices via `lsblk`
- **Device Type Filtering**: Select Pi model to filter compatible OSes
- **Local File Flashing**: Browse and flash local `.img`, `.img.xz`, `.zip`, `.iso` files
- **Decompress Support**: Built-in XZ and ZIP decompression
- **Configuration**: SSH and Wi-Fi setup options (placeholder for future injection)
- **Progress Tracking**: Real-time progress bar with speed display
- **Logging**: Activity log for operation status

## Requirements
```
pip install pyqt5 requests
```

## Usage
```bash
python main.py
```

## Controls
- **Device Type**: Select your Raspberry Pi model
- **Target Device**: Detected removable storage devices
- **Image File**: Browse for local image or select from OS list
- **Flash to Device**: Write image to selected storage

## Notes
- Requires root/admin privileges to write to devices
- Works on Linux (uses `lsblk` for device detection)
- Cached OS list in `~/.cache/rpi-imager/os-list.json`
- Configuration injection not yet implemented (planned)

## Source Reference
Icons and OS sources from: https://github.com/raspberrypi/rpi-imager# python-raspberry-imager
