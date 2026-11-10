# References: Blender-based structured light / FPP simulation

Collected 2026-11-10 while designing the Blender projector-camera simulation script.

Access status legend: `open` = full text retrieved, `abstract only` = publisher paywall,
`unverified` = could not locate the source at all.

## Inventory

| File | Paper | Access |
|---|---|---|
| `weston2026_digital_twin.pdf` | Weston et al., *Using a Digital Twin for Fringe Projection Profilometry Optimisation*, arXiv:2605.18545v1, 2026-05-18 | open |
| — | Puljčan, Zoraja, Petković, *Simulation of Structured Light 3D Scanning using Blender*, ELMAR 2022, pp. 215-220 | abstract only (IEEE, CLOSED) |
| — | Li et al., *Single-Model Self-Recovering Fringe Projection Profilometry Absolute Phase Recovery Method Based on Deep Learning*, Sensors 25(5):1532, 2025-03-01 | open (HTML read; PDF blocked by reCAPTCHA) |
| — | Zoraja, Petković, Forest, Pribanić, *Calibration of a Structured Light Imaging System in Two-Layer Flat Refractive Geometry for Underwater Imaging*, Sensors 23(12):5444, 2023-06-08 | open (HTML read; PDF blocked by reCAPTCHA) |
| — | Maglić, *Simulacija oslikavanja strukturiranim svjetlom u Blenderu i kalibracija virtualnog projektora i kamere*, FER (Univ. of Zagreb) bachelor thesis, 2021 | metadata only (repository returns HTTP 418) |

PDF note: `pmc.ncbi.nlm.nih.gov` and `europepmc.org` both rejected PDF downloads with
HTTP 403 / reCAPTCHA during collection. Only the HTML full text was retrieved, and only
the key facts are recorded below.

## Puljčan et al. 2022 (ELMAR)

DOI `10.1109/ELMAR55880.2022.9899809`. Abstract retrieved via the Semantic Scholar
Graph API; the full text is closed access.

> Many different optical setups and patterns are proposed for structured light 3D surface
> scanning. It is difficult and time consuming to experimentally assess all imaging options
> and to select the best one for a particular application. An efficient way of assessing
> imaging options is simulation of 3D scanning on a computer. We describe an efficient and
> low cost approach to simulating structured light scanning using Blender. Blender is an
> open source 3D computer graphics program primarily intended for 3D drawing and animation
> also supporting Phyton scripting to extend its capabilities. We describe how to simulate a
> simple scanning setup comprised of one camera, one projector, and one object. We also
> provide detailed description how to set both intrinsic and extrinsic parameters of
> projector and camera and discuss how to automate the simulation. To assess the correctness
> of the proposed simulation we simulate a real-world 3D surface scanner and we compare
> simulation results to the real-world results. We also perform experiments of scanning
> calibration objects. The proposed simulation method is correct and can be use to assess
> imaging geometry, to select structured light patterns, or to generate data for novel
> pattern decoders which use deep learning.

Relevance: confirms the two design axes of this project (configurable intrinsics/extrinsics,
scripted automation) and the validation approach (simulate a real scanner, compare against
real measurements, plus scans of calibration objects).

## Weston et al. 2026 (arXiv, digital twin)

DOI-equivalent: arXiv:2605.18545v1. Full PDF in this directory.

Abstract (verbatim):

> Fringe projection profilometry (FPP) is a widely used technique for measuring object
> surface form and three-dimensional (3D) geometry, capable of delivering high-precision,
> high-resolution measurements when paired with suitable cameras and projectors. However, in
> practical deployments, identifying parameter configurations that maximise precision while
> satisfying real-world constraints remains challenging. To address this, we present an
> automated digital twin framework implemented in Blender, an open-source 3D software package
> that provides a ray-traced rendering environment that enables accurate simulation of
> physical systems. We first replicated the physical setup in our digital twin by matching
> characterisation quality, gamma response, and characterisation images. Accurate system
> characterisation using Zhang's method [1], to obtain intrinsic and extrinsic parameters, is
> shown to be critical for achieving high precision. Using this digital twin, we then
> demonstrate systematic exploration and optimisation of key parameters, including
> phase-shift count, camera-projector spacing, and fringe density. These parameters span both
> system geometry (e.g. camera-projector positioning) and algorithmic choices, such as 2D
> phase-shifting and unwrapping methods [2]. Three measurement artefacts, representative of
> real-world metrology scenarios, were used to benchmark the system. The symmetrical mean
> Chamfer distance (SMCD), computed between ground-truth and reconstructed meshes, was used to
> evaluate reconstruction quality. After optimisation within the digital twin, transferring
> the optimal parameters to the physical system reduced the number of required images per
> measurement by 48% (from 36 to 21). A reduction of 74.0% mean SMCD was also achieved for
> fringe pattern stripe count alteration. A 36.9% mean SMCD was obtained for adjusting the
> camera and projector spacing purely in the digital-twin. These results demonstrate that
> optimising an FPP system using a digital twin can significantly improve reconstruction
> quality while reducing measurement effort in real-world metrology applications.

Key facts used in design decisions:

- §2.2 Blender Implementation: projectors are not natively supported; the authors wrote a
  custom add-on that emulates a projector through Blender's shader pipeline. **Cycles is
  mandatory** for correct projector behaviour.
- §2.2: Blender light "power" (watts) and emission strength have no direct physical
  counterpart to candela/lumens; the twin must encode the mapping explicitly.
- §2.3 Gamma Matching, Eq. (1): radiometric response `I_out = a * I_in^g + b`; matched
  against the physical system by non-linear least squares.
- §3.1: physical rig 1.20 m baseline, DLP4500 + Basler acA5472-17um, 12-step phase shifting,
  stripe counts (1, 8, 64).
- §3.2 and Fig. 10: average symmetric mean Chamfer distance between virtual and physical
  reconstruction was 13 micrometre for three artefacts, **with the virtual system performing
  about 19% better**; the authors attribute this to perfectly in-focus images with infinite
  depth of field and less noise.

Consequence for us: an ideal-pinhole projector will systematically over-estimate accuracy.
The simulator is good for algorithm development and data generation, not for claiming
physical measurement precision.

## Li et al. 2025 (Sensors, virtual measurement system)

DOI `10.3390/s25051532`. Full HTML read, PDF unavailable.

Key facts:

- §3.1: virtual measurement system built in Blender 4.0 from the calibration parameters of
  the physical rig (DLP3010 1280x720, Hikvision MV-CA016-10UM 1440x1080).
- §3.1: "we added aberration parameters to the nodes and renderer of the virtual projector"
  to match physical intrinsics, citing Zhang et al. and Wang et al.
- Table 2, virtual vs real projector distortion: k1 0.1315 vs 0.1328, k2 -0.3358 vs
  -0.3361, p1 -0.0006 vs -0.0006, p2 -0.0001 vs -0.0001. Camera k1 -0.1237 vs -0.1251.
- Table 3: virtual extrinsics match physical extrinsics to the printed precision.
- §3.1: rendering with varying projector power in the 5-60 W range used to simulate ambient
  light interference; all operations automated through the Python interface.

Consequence for us: this is direct evidence that the ideal-pinhole projector is *not*
sufficient to match a physical projector, and that distortion must be injected at the
shader-node level. It also shows camera distortion is of comparable magnitude to projector
distortion (|k1| about 0.12 for both).

## Zoraja et al. 2023 (Sensors, underwater calibration)

DOI `10.3390/s23125444`. Full HTML read, PDF unavailable. Same research group as Puljčan
et al. Provides the projector-as-inverse-camera calibration background (§3.4) and the
coplanarity / frustum / back-projection error decomposition (§3.5) used when the projector
is calibrated through camera observations. Relevant only if the simulated camera-projector
pair is later used to exercise calibration code.

## Unverified claim: University of Bologna thesis, section 3.1.2

A previous discussion attributed the seven-node projector shader network to a University of
Bologna thesis, section "3.1.2 Structured Light Projector Setup". **This source could not be
located** through web search or site-restricted search of `amslaurea.unibo.it`. It must not
be cited as a reference.

The method itself is independently corroborated by:

- dragly.org, "Structured light, part one", 2020-06-05, section "Setting up a basic projector
  and camera in Blender". Describes Texture Coordinate (Normal) -> Separate XYZ -> divide by
  Z -> image texture, and explains why the division by Z is required (normals are projected
  from a unit sphere, so rays hitting a plane at different distances land at the wrong
  texture coordinate).
- `Ocupe/Projectors` Blender add-on, `projector.py`, master branch. Same node chain; for
  Blender >= 4.0 it replaces `Texture Coordinate -> Normal` with
  `Geometry -> Incoming` + `Vector Transform`, then divides X and Z, Y and Z, and flips the
  mapping scale on X and Y.
