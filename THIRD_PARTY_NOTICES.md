# Third-party notices

AmneziaDashboard is independent and is not affiliated with or endorsed by Amnezia.
AmneziaVPN and AmneziaWG names and application UI belong to their respective
owners. The dashboard monogram is original project artwork.

- [Amnezia client](https://github.com/amnezia-vpn/amnezia-client): installed
  separately from official releases. See its repository for current licensing
  and the rights applying to its UI/screenshots. The two cropped UI screenshots
  illustrate manual key import only; this project's MIT grant does not relicense
  third-party artwork.
- [AmneziaWG Go](https://github.com/amnezia-vpn/amneziawg-go) and tools: downloaded
  from official upstream images by the installer, not embedded as VPN binaries
  in the source archive. Their licenses remain applicable.
- [acme.sh](https://github.com/acmesh-official/acme.sh): downloaded at installation
  time from its verified upstream commit; its own license applies.
- Flask, Gunicorn, Argon2, cryptography, Paramiko and their dependencies are
  installed separately using pinned requirements. See package metadata for
  individual licenses. Optional frozen Windows builds must carry dependency
  license texts collected from the build environment.
- Docker base images, Python and nginx retain their upstream licenses.
- QR encoding uses the local, unmodified Project Nayuki QR Code generator 1.8.0
  (MIT), ES6 release asset `qrcodegen-v1.8.0-es6.js`. Its full license is retained
  in `installer/portable/app/static/qrcodegen.js`. Upstream:
  https://github.com/nayuki/QR-Code-generator/releases/tag/v1.8.0 . SHA-256:
  `6a1116192ed1dd67fa1bf31e77f5817103d71c23bbac24c382e698b7668bdd01`.
  No external QR service, CDN or telemetry is used.
- Windows EXE includes Python, Tcl/Tk, Paramiko and crypto dependencies. The
  release carries Windows-licenses.zip and embeds the same collected notices.
  Reviewed Tcl/Tk terms are retained in docs/licenses from the official
  tcltk/tcl and tcltk/tk core-8-6-13 license.terms; runtime distributions may
  omit those text files while retaining the applicable Tcl/Tk license.

No production configuration, private certificate, customer/device database,
issued profile or user-specific invitation is part of this source release.
