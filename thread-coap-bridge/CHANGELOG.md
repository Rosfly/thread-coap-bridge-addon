# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-08

### Added
- Initial release
- CoAP multicast discovery for Thread devices
- Automatic device registration via `/.well-known/core`
- MQTT Discovery integration
- CoAP Observe support for real-time state updates
- Support for lights, switches, and sensors
- Battery level monitoring
- SQLite device registry
- Configuration via Home Assistant UI
- Multi-architecture support (amd64, aarch64, armv7)

### Known Issues
- DTLS encryption not yet supported (Thread provides MAC-layer encryption)
- Resource Directory (RD) mode not implemented
- No OTA firmware update support

## [Unreleased]

### Planned
- CoAP DTLS support for application-layer encryption
- Resource Directory mode for large deployments
- Custom resource type mapping
- Device grouping and bulk operations
- Metrics and statistics dashboard
