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
- Windows EXE includes Python, Tcl/Tk, Paramiko and crypto dependencies. The
  release carries Windows-licenses.zip and embeds the same collected notices.
  Reviewed Tcl/Tk terms are retained in docs/licenses from the official
  tcltk/tcl and tcltk/tk core-8-6-13 license.terms; runtime distributions may
  omit those text files while retaining the applicable Tcl/Tk license.

No production configuration, private certificate, customer/device database,
issued profile or user-specific invitation is part of this source release.
