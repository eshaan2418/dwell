# Dwell: Prior-Work Review

**Date of review:** 2026-10-24
**Method:** Every entry below was checked by web search (and, where possible, a page fetch) on 2026-10-24. Nothing is cited from memory alone. For each entry we confirmed the title, the authors or organization, the year, and a venue or URL that we actually saw. We did not add DOIs unless a search result showed them, and we give URLs rather than build DOI links. Where sources disagreed (versions, numbers, author lists), we say so. We searched the nine categories Dwell overlaps: sun-exposure apps; noise maps and noise-for-housing products; phone scanning and floor-plan capture; daylight and thermal simulation tools; scene-to-physics inference and building digital twins; uncertainty quantification; low-cost sensing and validation standards; decision and housing studies; and public datasets.

**How to read the "relevance" notes:** they say what Dwell can reuse, compare against, or must distinguish itself from. They are not summaries of the papers.

---

## 1. Sun-path and sun-exposure apps and products

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Sun Seeker | Ajnaware (iOS/Android app) | ongoing | https://apps.apple.com/us/app/sun-seeker-sunlight-tracker/id330247123 | AR camera overlay of the sun path, built from GPS, magnetometer and gyroscope. It shows the sky path from where the user stands but does not compute obstruction-aware sun hours per room. Baseline for the "what users already have" condition. |
| Sun Surveyor | Adam Ratana | ongoing | https://www.sunsurveyor.com/ | AR "Live View" of sun and moon paths, plus an ephemeris. Same gap: geometry only, no building obstruction model and no indoor quantity. |
| SunCalc.org | Torsten Hoffmann | ongoing | https://www.suncalc.org/ | Map-based sun azimuth and elevation for any date. Useful as a sanity check for Dwell's solar-geometry module. It has no obstruction model. |
| suncalc (JS library) | Vladimir Agafonkin | ongoing | https://github.com/mourner/suncalc | Lightweight open-source sun-position code. A lower-accuracy alternative to NREL SPA. |
| Shadowmap (Home / Studio) | Shadowmap | ongoing | https://shadowmap.org/ ; https://shadowmap.org/solutions/shadowmap-home/home-seeker | Global 3D sun and shadow simulation of buildings and terrain, sold to home seekers and to property platforms. **This is the closest commercial work for Dwell's sun output.** It works from the outside, at building or address level. We saw no evidence that it models per-room window apertures from an interior scan or reports calibrated uncertainty. |
| Redfin Sunscore | Redfin, co-developed with Shadowmap | 2026 (launched 11 May 2026) | https://www.redfin.com/news/press-releases/sunscore-launches-on-redfin-to-show-homebuyers-how-much-sunlight-a-home-gets/ | A 0–100 sunlight score on every US for-sale Redfin listing. It accounts for the building's structure, surrounding buildings, tree canopy and seasons. This shows that listing-level sun scores now exist at scale, so Dwell cannot claim novelty for "sun information for home buyers". Dwell's difference is per-room, interior-aperture, hours-based output with intervals. |
| Localize.city sunlight and noise insights | Localize (NYC) | c. 2018–2020 | https://www.localize.city/ ; http://www.localize.city/blog/localize-offers-sunlight-analysis-as-a-way-for-buyers-to-look-into-the-future | Uses LiDAR and 3D building models to estimate sunlight per building side across the year in NYC, alongside listing-level noise and nuisance flags. Prior art for joint sun and noise information on listings, at building-side level. |
| SunCheck | suncheckapp.com | ongoing | https://suncheckapp.com/ | Estimates daily direct-sun hours for an apartment from an address plus the direction the windows face, with a seasonal breakdown. Very close to Dwell's sun output in framing. It relies on user-entered orientation and does not scan the room. |
| Will It Be Bright? | willitbebright.com | ongoing | https://willitbebright.com/ | Takes an address or Zillow/Redfin link and estimates hourly sunlight for the front, back, left or right side of a unit. Another listing-level sun estimator. |

## 2. City noise maps and noise-for-housing products

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Environmental Noise Directive (END) reported data / strategic noise maps | European Environment Agency (EEA) | rounds 2007, 2012, 2017, 2022 (2022 data released Nov 2024) | https://www.eea.europa.eu/en/datahub/datahubitem-view/c952f520-8d71-42c9-b74c-b7eb002f939b | Lden and Lnight exposure counts and noise contours for EU agglomerations, roads, railways and airports. The reference example of an outdoor façade-level noise map. Dwell needs the outdoor-to-indoor step that these maps do not provide. |
| CNOSSOS-EU: Common Noise Assessment Methods in Europe | Kephalopoulos, Paviotti, Anfosso-Lédée (EC JRC), EUR 25379 EN | 2012 | https://publications.jrc.ec.europa.eu/repository/handle/JRC72550 | The harmonized road, rail, aircraft and industrial noise calculation method behind Annex II of the END. A candidate for Dwell's outdoor façade-level estimate where no measured map exists. |
| Advances in the development of CNOSSOS-EU | Kephalopoulos et al., *Science of the Total Environment* | 2014 | https://pubmed.ncbi.nlm.nih.gov/24582156/ | Companion paper describing how the framework was developed and the problems in implementing it. |
| National Transportation Noise Map | US DOT Bureau of Transportation Statistics | 2017, updated (2016/2018 layers, Nov 2020) | https://www.bts.gov/geospatial/national-transportation-noise-map | 24-h LAeq for aviation, road and rail. It ignores shielding and is explicitly **not** meant for individual locations. A cautionary example: Dwell needs façade and obstruction-aware estimates. |
| Environmental Noise Study in the City of Toronto | Toronto Public Health | 2017 | https://www.toronto.ca/wp-content/uploads/2017/11/8f4d-tph-Environmental-Noise-Study-2017.pdf | Toronto-specific monitoring and modelling (land-use regression plus propagation), producing LAeq,16h, LAeq,8h and Lmax surfaces. **The most relevant outdoor noise prior for Dwell's Toronto deployment.** |
| Exploring nighttime road traffic noise: a comprehensive predictive surface for Toronto, Canada | *J. Occupational and Environmental Hygiene* 15:389–398 (author list per a citing JAHA paper: Drudge, Johnson, MacIntyre, Li, Copes, Ing, Johnson, Varughese, Chen; byline not directly confirmed) | 2018 | https://www.tandfonline.com/doi/full/10.1080/15459624.2018.1442006 | Night-time road-noise surface for Toronto built from 767 measurement sites (2012–2013). A direct candidate for Dwell's outdoor Lnight input. |
| HowLoud / Soundscore | HowLoud | 2015– | https://howloud.com/ ; https://howloud.com/faqs | Address-level noise score (traffic, air traffic, local sources; road traffic via the FHWA Traffic Noise Model). The main commercial noise-for-housing product. It reports outdoor neighbourhood noise, not indoor bedroom levels, and user reports question its accuracy. |
| NoiseTube: measuring and mapping noise pollution with mobile phones | Maisonneuve, Stevens, Niessen, Steels (ITEE 2009, Springer) | 2009 | https://link.springer.com/chapter/10.1007/978-3-540-88351-7_16 | Participatory phone-based noise mapping. Uploads exposure values only, with no audio, which is an early privacy-by-design precedent for Dwell's dB-only microphone. |
| SONYC: a system for monitoring, analyzing, and mitigating urban noise pollution | Bello et al., *Communications of the ACM* 62(2):68–77 | 2019 | https://dl.acm.org/doi/abs/10.1145/3224204 | Low-cost (~$80) calibrated acoustic sensor network reaching ANSI Type-2 accuracy, plus machine listening. The precedent for low-cost calibrated SPL sensing. Outdoor and city-scale. |
| Differences between outdoor and indoor sound levels for open, tilted, and closed windows | Locher et al., *IJERPH* 15(1):149 | 2018 | https://www.mdpi.com/1660-4601/15/1/149 | Paired indoor/outdoor measurements in 102 Swiss homes (living room and bedroom), with a statistical model of the outdoor–indoor level difference. **The closest academic prior for Dwell's indoor-noise step**, though the measurements were short (~3 min). |
| An outdoor-to-indoor sound propagation modelling framework for evaluating noise exposure applications | *Acta Acustica* (2025) (authors not retrieved; page fetch blocked) | 2025 | https://acta-acustica.edpsciences.org/articles/aacus/full_html/2025/01/aacus250070/aacus250070.html | Framework combining noise maps with façade-insulation physics (single to triple glazing). It reports that indoor SPL is governed mainly by the outdoor level. Directly comparable to Dwell's physics path. |

## 3. Scanning apps and floor-plan capture

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| RoomPlan | Apple | 2022 (WWDC22), enhanced 2023 | https://developer.apple.com/documentation/roomplan ; https://developer.apple.com/videos/play/wwdc2023/10192/ | Camera + LiDAR API producing parametric rooms (walls, windows, doors, furniture) as USD/USDZ. Likely the input layer for Dwell on LiDAR iPhones. It captures geometry only, with no envelope properties. |
| Polycam | Polycam | ongoing | https://poly.cam/ | LiDAR/photogrammetry capture and floor plans with OBJ/GLB/USDZ/DXF export. An alternative capture front-end. |
| magicplan | magicplan (Sensopia) | ongoing | https://magicplan.app/ | Floor plans from the phone camera or LiDAR, with estimating workflows for restoration and insurance. Shows that floor-plan capture is commoditized. |
| Matterport for iPhone | Matterport | LiDAR support 2020– | https://matterport.com/blog/matterport-iphone-lidar-support-here | Phone-based digital-twin capture. Commercial benchmark for the "2-minute walkthrough" UX. |
| Canvas (renamed Twindo, Feb 2026) | Occipital | ongoing | https://illustrarch.com/articles/design-softwares/110335-canvas-occipital-review.html | LiDAR scan to CAD floor plans (paid, with human-in-the-loop drafting). Another geometry-only capture tool. |
| Zillow Indoor Dataset (ZInD) | Cruz, Hutchcroft, Li, Khosravan, Boyadzhiev, Kang (CVPR 2021) | 2021 | https://openaccess.thecvf.com/content/CVPR2021/html/Cruz_Zillow_Indoor_Dataset_Annotated_Floor_Plans_With_360deg_Panoramas_and_CVPR_2021_paper.html ; https://github.com/zillow/zind | 360° panoramas from about 1,500 unfurnished homes, with floor plans and window/door locations. Useful for training or evaluating window and room layout. Access requires manual academic approval. |
| Energy-audit LiDAR apps (e.g., Energy Intelligence, autarc) | vendors | ongoing | https://www.autarc.energy/global/products/lidar-scan ; https://www.energyintelligence.ai/blog/future-of-energy-audits-ai-driven-intelligence | Commercial phone-LiDAR-to-heat-load workflows (autarc: DIN EN 12831 heat load). **Adjacent prior art for "phone scan → thermal model".** Aimed at professionals sizing heating, not at renters, and with no reported uncertainty. Claims are vendor-reported. |

## 4. Daylight, solar and thermal simulation tools

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| The RADIANCE lighting simulation and rendering system | G. J. Ward, SIGGRAPH '94 | 1994 | https://dl.acm.org/doi/10.1145/192161.192286 ; https://floyd.lbl.gov/radiance/papers/sg94.1/paper.html | The validated reference for daylight simulation. Candidate "gold" engine for checking Dwell's fast ray-cast sun model. |
| DAYSIM / dynamic Radiance-based daylight simulation (validation for a test office with external blinds) | Reinhart & Walkenhorst | 2001 | https://www.researchgate.net/publication/245196744_Validation_of_dynamic_RADIANCE-based_daylight_simulation_for_a_test_office_with_external_blinds | Climate-based annual daylight using daylight coefficients and the Perez sky. Precedent for annual metrics computed from weather files. |
| ClimateStudio | Solemma | ongoing (2.0 RC 2024) | https://www.solemma.com/climatestudio | Rhino plugin with a Radiance-based path tracer and EnergyPlus. The professional benchmark for daylight and energy. Too heavy for a phone loop. |
| Ladybug (and Honeybee) | Sadeghipour Roudsari & Pak, Building Simulation 2013 (IBPSA, Chambéry) | 2013 | https://www.ladybug.tools/publication.html ; https://github.com/ladybug-tools/honeybee-legacy | Open-source wrappers for EPW, Radiance, Daysim and EnergyPlus. A convenient way to generate reference runs for Dwell's validation. |
| EnergyPlus: creating a new-generation building energy simulation program | Crawley et al., *Energy and Buildings* 33(4):319–331 | 2001 | https://www.sciencedirect.com/science/article/abs/pii/S0378778800001146 | Detailed whole-building simulation. Candidate high-fidelity reference for Dwell's 5R1C thermal model. |
| ISO 13790:2008 (simple hourly method, 5R1C) | ISO | 2008 | https://www.iso.org/standard/41974.html | The 5R1C lumped thermal network Dwell's heat model is based on. |
| ISO 52016-1:2017 | ISO | 2017 (confirmed 2022) | https://www.iso.org/standard/65696.html | Successor hourly method for energy needs and **internal temperatures**. Dwell should say whether it follows 13790 or 52016-1 and why. |
| RC_BuildingSimulator | Architecture and Building Systems group (ETH), Jayathissa et al. | 2017– | https://github.com/architecture-building-systems/RC_BuildingSimulator | Open-source Python 5R1C (ISO 13790) implementation. Possibly reusable directly, or as a cross-check. |
| pvlib python | Holmgren, Hansen, Mikofski, *JOSS* 3(29):884 | 2018 | https://joss.theoj.org/papers/10.21105/joss.00884 | BSD-3 solar position, clear-sky and transposition models. A practical dependency for Dwell's solar module. |
| Solar Position Algorithm for Solar Radiation Applications | Reda & Andreas, *Solar Energy* 76(5):577–589 (NREL/TP-560-34302) | 2004 | https://docs.nrel.gov/docs/fy08osti/34302.pdf ; https://midcdmz.nrel.gov/spa/ | ±0.0003° solar position. The reference algorithm Dwell should cite for sun geometry. |
| ML surrogates for daylight (e.g., the review "A review and guide on selecting and optimizing machine learning algorithms for daylight prediction") | *Building and Environment* | 2023 | https://www.sciencedirect.com/science/article/abs/pii/S0360132323008491 | ANN/CNN/GAN surrogates for sDA, ASE and illuminance are well established for early design. Dwell's learned components are not novel as "ML daylight surrogates". |

## 5. Scene-to-physics inference and building digital twins

### 5a. Inferring envelope and building properties from images

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| A method for using street view imagery to auto-extract window-to-wall ratios and its relevance for urban-level daylighting and energy simulations | Szcześniak, Ang, Letellier-Duchesne, Reinhart, *Building and Environment* 207:108108 | 2021/2022 | https://www.sciencedirect.com/science/article/abs/pii/S0360132321005096 | Street-view WWR extraction feeding urban energy and daylight models. The closest precedent for "image → envelope parameter → physics". Exterior, urban scale. |
| Detecting window-to-wall ratio for urban-scale building simulations using deep learning with street view imagery and an automatic classification algorithm | Suppa, Aliberti, Bottero, Corrado, *Building Simulation* 18(8):2175–2199 | 2025 | https://www.sciopen.com/article/10.1007/s12273-025-1301-3 | YOLOv9 WWR from Google Street View, with extension to non-street façades. |
| Window detection in facade imagery: a deep learning approach using Mask R-CNN | arXiv 2107.10006 | 2021 | https://arxiv.org/abs/2107.10006 | Window instance segmentation on façades. Detects windows but does not identify glazing type. |
| Estimating building energy efficiency from street view imagery, aerial imagery, and land surface temperature data | Mayer, Haas, Huang, Bernabé-Moreno, Rajagopal, Fischer (arXiv 2206.02270) | 2022 | https://arxiv.org/abs/2206.02270 | End-to-end EPC-class prediction (A–D vs E–G, macro-F1 ≈ 0.65) for about 40k UK buildings. **Prior art for inferring hidden energy-relevant properties from imagery.** Building-level and classification-only, with no physics or interval coverage. |
| Towards an automated image-based estimation of building age as input for Building Energy Modeling (BEM) | Benz, Voelker, Daubert, Rodehorst, *Energy and Buildings* | 2023 | https://www.sciencedirect.com/science/article/abs/pii/S0378778823003961 | Building age from images as a BEM input (age → typology → U-values). Directly analogous to Dwell's "building metadata → envelope prior". |
| Material recognition in the wild with the Materials in Context Database (MINC) | Bell, Upchurch, Snavely, Bala, CVPR 2015 | 2015 | https://arxiv.org/abs/1412.0623 | Large-scale material recognition (23 classes). Possible visual cue extractor for wall and floor materials that feed Dwell's mass and absorption priors. |
| In-situ U-value by infrared thermography (e.g., pixel-level method, arXiv 2401.07163) | arXiv | 2024 | https://arxiv.org/abs/2401.07163 | Thermography gives U-values directly but needs a thermal camera and an indoor–outdoor temperature gradient. A possible ground-truth path for Dwell's envelope priors in a validation subset. |

### 5b. Gray-box / hybrid physics–ML building thermal models

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Identifying suitable models for the heat dynamics of buildings | Bacher & Madsen, *Energy and Buildings* 43(7):1511–1522 | 2011 | https://orbit.dtu.dk/en/publications/identifying-suitable-models-for-the-heat-dynamics-of-buildings/ | The canonical stochastic gray-box RC identification and model-selection procedure. Dwell's RC fitting on sensor data should follow or compare against it. |
| Control-oriented inverse modeling of the thermal characteristics in an office | Gunay, O'Brien, Beausoleil-Morrison, *Science and Technology for the Built Environment* 22(5) | 2016 | https://www.tandfonline.com/doi/abs/10.1080/23744731.2016.1175893 | Twelve gray-box models identified with Kalman/particle filtering. Precedent for estimating RC parameters from sparse sensors. |
| Identifying grey-box thermal models with Bayesian neural networks | Hossain, Zhang, Ardakanian, *Energy and Buildings* 238:110836 | 2021 | https://arxiv.org/abs/2009.05889 | Uses ecobee data from 8,884 homes. Shows that **priors on RC parameters from similar homes (floor area, age, climate) speed up identification for a new home.** This is the closest analogue to Dwell's "metadata → learned prior on hidden properties", but driven by thermostat data rather than visual scans. |
| Physics-constrained deep learning of multi-zone building thermal dynamics | Drgoňa, Tuor, Chandan, Vrabie, *Energy and Buildings* 243 | 2021 | https://arxiv.org/abs/2011.05987 | Physics-structured recurrent model with eigenvalue constraints. A representative physics-informed ML baseline. |
| Integrating physics-based and data-driven approaches for probabilistic building energy modeling | Von Krannichfeldt, Orehounig, Fink, *Energy and Buildings* 353:116838 | 2025/2026 | https://www.sciencedirect.com/science/article/pii/S0378778825015683 | Five hybrid physics–ML schemes (including residual correction) in a probabilistic quantile framework, **calibrated with conformalized quantile regression**, with a real case study for indoor temperature. **The closest academic prior to Dwell's contribution 2 for the heat output.** |
| Calibration of building energy models for retrofit analysis under uncertainty | Heo, Choudhary, Augenbroe, *Energy and Buildings* 47:550–560 | 2012 | https://www.sciencedirect.com/science/article/abs/pii/S037877881100644X | Kennedy–O'Hagan Bayesian calibration (parameter uncertainty, model discrepancy, observation error) for building models. The Bayesian alternative to Dwell's conformal approach. |
| Bayesian calibration of computer models | Kennedy & O'Hagan, *JRSS-B* 63:425–450 | 2001 | (cited via https://www.tandfonline.com/doi/full/10.1080/19401493.2018.1475506) | The foundational model-discrepancy framework. Dwell's "learned residual" is a discrepancy term in this sense. |

### 5c. Acoustic property estimation from images and scans

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Acoustic classification and optimization for multi-modal rendering of real-world scenes | Schissler, Loftin, Manocha, *IEEE TVCG* 24(3):1246–1259 | 2017/2018 | http://gamma.cs.unc.edu/AClassification/ | CNN material classification on reconstructed 3D scenes, giving absorption coefficients and then optimization against measured IRs. Prior art for inferring acoustic material properties from scans. It targets room acoustics, not façade insulation. |
| Image2Reverb: cross-modal reverb impulse response synthesis | Singh, Mentch, Ng, Beveridge, Drori, ICCV 2021 | 2021 | https://arxiv.org/abs/2103.14201 | Single image → room impulse response. Visual-to-acoustic inference, but for reverberation, not transmission loss. |
| Visual Acoustic Matching (AViTAR) | Chen, Gao, Calamia, Grauman, CVPR 2022 | 2022 | https://arxiv.org/abs/2202.06875 | Image-conditioned re-reverberation of audio. Same distinction as Image2Reverb. |
| Listen2Scene: interactive material-aware binaural sound propagation for reconstructed 3D scenes | Ratnarajah & Manocha, IEEE VR 2024 | 2023/2024 | https://arxiv.org/abs/2302.02809 | GNN over a reconstructed mesh with material properties, producing binaural IRs. Prior art for "phone-scale reconstruction → acoustic simulation". Interior propagation only. |

### 5d. Indoor 3D reconstruction, layout, open-vocabulary perception and depth

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Structure-from-Motion Revisited (COLMAP) | Schönberger & Frahm, CVPR 2016 | 2016 | https://openaccess.thecvf.com/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html ; https://colmap.github.io/ | Standard SfM/MVS (BSD). Pose recovery for non-LiDAR phones. |
| Global Structure-from-Motion Revisited (GLOMAP) | Pan, Baráth, Pollefeys, Schönberger, ECCV 2024 | 2024 | https://arxiv.org/abs/2407.20219 | Faster global SfM with accuracy comparable to COLMAP. Note that the standalone repo is now marked deprecated. |
| 3D Gaussian Splatting for real-time radiance field rendering | Kerbl, Kopanas, Leimkühler, Drettakis, ACM TOG 42(4) (SIGGRAPH 2023) | 2023 | https://arxiv.org/abs/2308.04079 | Scene representation for walkthrough video. |
| SuGaR: surface-aligned Gaussian splatting for efficient 3D mesh reconstruction | Guédon & Lepetit, CVPR 2024 | 2024 | https://arxiv.org/abs/2311.12775 | Mesh extraction from 3DGS. Gives Dwell geometry for ray casting. |
| 2D Gaussian Splatting for geometrically accurate radiance fields | Huang, Yu, Chen, Geiger, Gao, SIGGRAPH 2024 | 2024 | https://arxiv.org/abs/2403.17888 | Better surface geometry than 3DGS. The authors note it struggles with glass and semi-transparent surfaces, **which is directly relevant because windows are Dwell's key apertures.** |
| SceneScript | Avetisyan et al. (Meta Reality Labs), ECCV 2024 | 2024 | https://arxiv.org/abs/2403.13064 | Video → structured layout commands (walls, doors, windows). A strong learned alternative to RoomPlan for layout from walkthroughs. |
| HorizonNet | Sun, Hsiao, Sun, Chen, CVPR 2019 | 2019 | https://arxiv.org/abs/1901.03861 | Panorama room-layout estimation baseline. |
| Grounding DINO | Liu et al., ECCV 2024 | 2023/2024 | https://arxiv.org/abs/2303.05499 | Open-set detection of text-prompted cues (e.g., "window frame", "radiator", "AC unit"). |
| Scaling Open-Vocabulary Object Detection (OWLv2) | Minderer, Gritsenko, Houlsby, NeurIPS 2023 | 2023 | https://arxiv.org/abs/2306.09683 | Alternative open-vocabulary detector. |
| Segment Anything | Kirillov et al., ICCV 2023 | 2023 | https://arxiv.org/abs/2304.02643 | Promptable masks for window and wall regions. |
| SAM 2: Segment Anything in Images and Videos | Ravi et al. | 2024 | https://arxiv.org/abs/2408.00714 | Video mask propagation across the walkthrough. |
| Depth Anything V2 | Yang, Kang, et al., NeurIPS 2024 | 2024 | https://arxiv.org/abs/2406.09414 | Metric-depth variants fine-tuned on Hypersim (indoor, max 20 m). Depth for non-LiDAR phones. |
| Metric3D v2 | Hu, Yin, et al., IEEE TPAMI | 2024 | https://arxiv.org/abs/2404.15506 | Zero-shot metric depth plus surface normals, handling camera intrinsics via a canonical camera space. |
| ZoeDepth | Bhat, Birkl, Wofk, Wonka, Müller | 2023 | https://arxiv.org/abs/2302.12288 | Relative-to-metric depth baseline. |
| Depth Pro | Bochkovskii et al. (Apple), ICLR 2025 | 2024/2025 | https://arxiv.org/abs/2410.02073 | Metric depth without intrinsics, with sharp boundaries (useful at window frames). |

## 6. Uncertainty: conformal prediction and sensitivity analysis

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Distribution-free predictive inference for regression | Lei, G'Sell, Rinaldo, Tibshirani, Wasserman, *JASA* 113(523):1094–1111 | 2018 | https://arxiv.org/abs/1604.04173 | Split conformal regression. The base method for Dwell's intervals. |
| Predictive inference with the jackknife+ | Barber, Candès, Ramdas, Tibshirani, *Annals of Statistics* 49(1):486–507 | 2021 | https://arxiv.org/abs/1905.02928 | Jackknife+ and CV+. Better suited to Dwell's small sensor-validated sample than split conformal. |
| Conditional validity of inductive conformal predictors | Vovk, ACML 2012 (PMLR 25) / *Machine Learning* 2013 | 2012 | https://arxiv.org/abs/1209.2673 | Category-conditional (Mondrian-style "m-taxonomy") validity. The basis for per-group coverage (e.g., by building age class or façade orientation). |
| Conformalized quantile regression | Romano, Patterson, Candès, NeurIPS 2019 | 2019 | https://arxiv.org/abs/1905.03222 | Adaptive-width intervals. Already used for building indoor temperature by Von Krannichfeldt et al. (5b). |
| A gentle introduction to conformal prediction and distribution-free uncertainty quantification | Angelopoulos & Bates (FnT ML 16(4), 2023) | 2021/2023 | https://arxiv.org/abs/2107.07511 | Tutorial reference for methods and pitfalls. |
| Quantifying uncertainty with conformal prediction for heating and cooling load forecasting in building performance simulation | Borrotti, *Energies* 17:4348 | 2024 | https://www.mdpi.com/1996-1073/17/17/4348 | Split conformal intervals on simulated building loads. **Shows that conformal prediction is already applied in building simulation.** |
| Variance based sensitivity analysis of model output: design and estimator for the total sensitivity index | Saltelli, Annoni, Azzini, Campolongo, Ratto, Tarantola, *Computer Physics Communications* 181:259–270 | 2010 | https://ui.adsabs.harvard.edu/abs/2010CoPhC.181..259S | The Saltelli sampling and total-index estimator for Dwell's Sobol propagation. |
| SALib: an open-source Python library for sensitivity analysis | Herman & Usher, *JOSS* 2(9):97 | 2017 | https://joss.theoj.org/papers/10.21105/joss.00097 | MIT-licensed Sobol/Morris implementation. A practical dependency. |
| A review of sensitivity analysis methods in building energy analysis | W. Tian, *Renewable and Sustainable Energy Reviews* 20:411–419 | 2013 | https://ideas.repec.org/a/eee/rensus/v20y2013icp411-419.html | Establishes global and variance-based SA as standard practice in building simulation. |
| Climate change influence on buildings dynamic thermal behavior during summer overheating periods: an in-depth sensitivity analysis | Machard, Inard, Alessandrini, Devys-Peyre, Martinez, Ribéron, Pelé (ScienceDirect, Energy and Buildings ISSN 0378-7788) | 2023 | https://www.sciencedirect.com/science/article/abs/pii/S037877882200929X | Morris plus Sobol on a free-running apartment. Thermal mass, glazing percentage, solar control and ventilative cooling dominate summer overheating. **These are exactly Dwell's hidden properties**, so it supports Dwell's choice of which properties to infer. |

## 7. Low-cost indoor sensing, validation and standards

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| The implementation of low-cost urban acoustic monitoring devices | Mydlarz, Salamon, Bello, *Applied Acoustics* 117:207–218 | 2017 | https://arxiv.org/abs/1605.08450 | Calibration of MEMS microphones to Type/Class-2-level dB readings (IEC 61672). The methodological template for calibrating Dwell's ESP32 microphone. |
| INMP441 datasheet | TDK InvenSense | 2015 | https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf | Sensitivity tolerance of ±3 dB (per a project that compared it with the ICS-43434 at ±1 dB: https://hackaday.io/project/166867-esp32-i2s-slm). So Dwell needs per-unit calibration, and the MEMS noise floor (~35 dB per that project) is close to quiet-bedroom night levels. **This is a serious validation risk.** |
| esp32-i2s-slm | I. Kostoski (GitHub) | ongoing | https://github.com/ikostoski/esp32-i2s-slm | Open-source ESP32 A-weighted SLM firmware. A reference implementation. |
| Performance assessment of low-cost environmental monitors and single sensors under variable indoor air quality and thermal conditions | Demanega, Mujan, Singer, Anđelković, Babich, Licina, *Building and Environment* 187 | 2021 | https://seta.lbl.gov/publications/performance-assessment-low-cost | Chamber evaluation of consumer temperature/RH monitors against research-grade instruments. |
| Low-cost thermohygrometers to assess thermal comfort in the built environment: a laboratory evaluation | Salamone, Chinazzo, Danza, Miller, Sibilio, Masullo, *Buildings* 12(5):579 | 2022 | https://www.mdpi.com/2075-5309/12/5/579 | Six of seven low-cost sensors met ISO 7726 accuracy. Linear correction is recommended. Supports Dwell's temperature/RH validity with a co-location calibration step. |
| Overheating in buildings: lessons from research | Lomas & Porritt, *Building Research & Information* 45(1–2):1–18 | 2017 | https://www.tandfonline.com/doi/full/10.1080/09613218.2017.1256136 | Low-cost temperature loggers have made large multi-month home monitoring campaigns routine. **So multi-week in-home temperature monitoring alone is not novel.** Also covers how hard bedroom overheating criteria are to apply. |
| Wireless temperature, relative humidity and occupancy monitoring system for investigating overheating in buildings | *Sensors* 22(22):8638 (MDPI) | 2022 | https://www.mdpi.com/1424-8220/22/22/8638 | Low-cost in-apartment overheating monitoring (bedrooms often above 30 °C). A protocol precedent. |
| Environmental Noise Guidelines for the European Region | WHO Regional Office for Europe | 2018 | https://www.who.int/europe/publications/i/item/9789289053563 | Road traffic: 53 dB Lden and 45 dB Lnight (outdoor). The health anchor for Dwell's noise output. |
| Night Noise Guidelines for Europe | WHO Regional Office for Europe | 2009 | https://www.who.int/europe/publications/i/item/9789289041737 | Outdoor Lnight 40 dB target, 55 dB interim target. |
| ISO 12354-3:2017 (EN ISO 12354-3) — airborne sound insulation against outdoor sound | ISO / CEN | 2017 | https://www.iso.org/standard/70244.html | The façade-insulation calculation model Dwell's noise physics implements. It includes indoor-level prediction (Annex E), and its results should be checked against field measurements made to ISO 16283-3. |

## 8. Decision and housing-search studies

| Name | Authors / Org | Year | URL | Relevance to Dwell |
|---|---|---|---|---|
| Valuing sunshine | Fleming, Grimes, Lebreton, Maré, Nunns, *Regional Science and Urban Economics* 68:268–276 | 2018 | https://ideas.repec.org/a/eee/regeco/v68y2018icp268-276.html | About +2.6% house price per extra daily hour of sun (working paper: 2.4%). Motivates "direct-sun hours" as the unit Dwell reports. |
| Impact of access to sunlight on residential property values: Shanghai | *International Journal of Strategic Property Management* | c. 2023 | https://journals.vilniustech.lt/index.php/IJSPM/article/view/18004 | About a 7.2% premium for high-sun, south-facing units. The premium shrinks with air pollution and grows with floor height. Apartment-level evidence. |
| Value of an apartment with sunlight and view: a quasi-experimental analysis | Jung, Kim, Hong (SSRN 4181988) | c. 2022 | https://papers.ssrn.com/sol3/Delivery.cfm/ebea40af-c4e6-4efd-a740-4fbb92cdbf57-MECA.pdf?abstractid=4181988 | Difference-in-differences estimate: sun plus view ≈ 16.2% of price. A causal design worth emulating. |
| Influence of daylight on real estate housing prices: Turin | *Journal of Building Engineering* (ScienceDirect) | 2024 | https://www.sciencedirect.com/science/article/pii/S2352710224019818 | Simulated annual sunlight exposure and UDI predicted prices, while DF and sDA did not. **Directly supports Dwell's metric choice (sun hours over daylight factor).** |
| Buyer information and the hedonic: the impact of a seller disclosure on the implicit price for airport noise | J. C. Pope, *Journal of Urban Economics* 63(2):498–516 | 2008 | https://ideas.repec.org/a/eee/juecon/v63y2008i2p498-516.html | Mandatory noise disclosure lowered prices of high-noise homes by about 2.9%, so buyers were under-informed. **The strongest evidence that giving noise information changes housing decisions**, and the motivation for Dwell's renter study. |
| Quasi-experimental evidence on the effect of aircraft noise on apartment rents | Boes & Nüesch, *Journal of Urban Economics* | 2011 | https://www.sciencedirect.com/science/article/abs/pii/S0094119010000719 | About −0.5% rent per dB. A rental-market (not sales) estimate, which matches Dwell's renter focus. |
| Hedonic analysis over time and space: the case of house prices and traffic noise | Swoboda, Nega, Timm, *Journal of Regional Science* | 2015 | https://onlinelibrary.wiley.com/doi/10.1111/jors.12187 | Road-noise hedonic evidence: a consistently negative relationship. |
| Property prices and exposure to multiple noise sources: hedonic regression with road and railway noise | Andersson, Jonsson, Ögren, *Environmental and Resource Economics* | 2010 | https://link.springer.com/article/10.1007/s10640-009-9306-4 | Road noise is discounted more than rail noise. Relevant to source-specific outputs. |
| When (ish) is my bus? User-centered visualizations of uncertainty in everyday, mobile predictive systems | Kay, Kola, Hullman, Munson, CHI 2016 | 2016 | https://dl.acm.org/doi/10.1145/2858036.2858558 | Quantile dotplots for mobile uncertainty. A candidate display for Dwell's intervals. |
| Uncertainty displays using quantile dotplots or CDFs improve transit decision-making | Fernandes, Walls, Munson, Hullman, Kay, CHI 2018 | 2018 | https://dl.acm.org/doi/10.1145/3173574.3173718 | An incentivized decision experiment: dotplots reached about 97% of optimal payoff. **The methodological template for Dwell's renter decision study.** |
| Uncertainty forecasts improve weather-related decisions and attenuate the effects of forecast error | Joslyn & LeClerc, *J. Experimental Psychology: Applied* 18(1):126–140 | 2012 | https://psycnet.apa.org/record/2011-18824-001 | Uncertainty information improved decisions **and trust** when forecasts were wrong. Directly relevant to how Dwell's intervals affect trust after a prediction misses. |
| Effect of confidence and explanation on accuracy and trust calibration in AI-assisted decision making | Zhang, Liao, Bellamy, ACM FAT* 2020 | 2020 | https://arxiv.org/abs/2001.02114 | Confidence displays calibrate trust but do not by themselves improve joint accuracy. A caution for how Dwell frames its hypotheses. |

## 9. Candidate public datasets (partial substitutes for missing in-home data)

| Dataset | Org / Citation | What it has | License / access (as verified) | Usable for Dwell? |
|---|---|---|---|---|
| IDEAL Household Energy Dataset | Goddard, Kilgour, Pullinger, et al. (U. Edinburgh); Pullinger et al., *Scientific Data* 2021 — https://www.nature.com/articles/s41597-021-00921-y ; https://datashare.ed.ac.uk/handle/10283/3647 | 255 UK homes over 23 months. **Per-room temperature, humidity and light at 12 s**, plus weather, surveys and building metadata. | DataShare lists an "End-user Licence" (terms not read). The article itself is CC BY. | **Yes, the best substitute for heat validation and partly for light.** Room light sensors give relative daylight signals. UK housing stock and climate, not Toronto. Check the end-user licence before redistributing anything. |
| ecobee Donate Your Data (DYD) | ecobee — https://www.ecobee.com/en-us/donate-your-data/ ; 2017 1,000-home sample on OSTI: https://www.osti.gov/biblio/1854924 | Indoor/outdoor temperature, HVAC runtime and home metadata (size, age) for more than 200k North American homes, including Canadian ones. | Partnership agreement required. Free to approved researchers, who must publish their findings. | **Yes, if access is granted.** The best North-American source for RC identification (cf. Hossain et al. 2021). It records thermostat location only, not per room, and HVAC confounds summer peak temperatures. |
| ASHRAE Global Thermal Comfort Database II | Földváry Ličina et al., *Building and Environment* 142:502–512 (2018) — https://datadryad.org/dataset/doi:10.6078/D1F671 | About 109k paired indoor-climate measurements and comfort votes. | Open on Dryad (Dryad licence not checked here). | Limited. Point-in-time comfort surveys, not time series. Useful for comfort thresholds, not for validating peak temperatures. |
| NoiseCapture data | Université Gustave Eiffel / Noise-Planet; Bocher et al., *Data in Brief* 14:498–503 (2017) — https://noise-planet.org/noisecapture_data.html | Crowd-sourced smartphone LAeq (1 s, with octave bands) and GPS tracks, worldwide. No audio. | **ODbL** (share-alike on derived databases). | Partly. Outdoor levels only, and fewer than two-thirds of measurement points come from user-calibrated phones. Could be a weak check on Toronto outdoor priors. |
| SONYC Urban Sound Tagging (SONYC-UST v2) | Cartwright et al. (NYU) — https://zenodo.org/records/3966543 | 18,510 ten-second NYC sensor clips with source labels and spatiotemporal context. | **CC BY 4.0** | Limited. Useful for source classification. It is not calibrated level time series or indoor data, and Dwell's dB-only design would not use audio anyway. |
| Toronto 3D Massing | City of Toronto Open Data — https://open.toronto.ca/dataset/3d-massing/ | Citywide building massing with heights. | **Open Government Licence – Toronto** | Yes. Already an input to Dwell's obstruction model. Check which vintage is current, since a 2015 release is documented. |
| OpenStreetMap | OSM Foundation — https://www.openstreetmap.org/copyright | Building footprints and height/levels tags, roads, transit. | **ODbL.** Attribution for public produced works; derivative training databases must stay ODbL if used publicly. | Yes. Note the share-alike obligation if Dwell releases derived geodata. |
| ECCC Historical Hourly Climate Data | Environment and Climate Change Canada — https://climate.weather.gc.ca/ ; https://eccc-msc.github.io/open-data/msc-data/climate_obs/readme_climateobs_en/ | Hourly station observations (Toronto stations included). | Governed by the ECCC/MSC end-user licence. We did **not** confirm it is OGL-Canada. | Yes, as weather input. Confirm the licence wording. |
| Sounds of Home | CVSSP, University of Surrey — https://www.cvssp.org/data/ai4s/sounds_of_home/ | 1,344 one-hour in-home audio recordings from 8 Belgian homes (living room and kitchen). | Terms not verified. | Weak. Not bedrooms, not Canadian, raw audio. Could test dB extraction only. |

We did **not** find an open, long-term, in-bedroom calibrated sound-level dataset or an open residential indoor-illuminance time-series dataset (see Gaps).

---

## What is and isn't new

The landscape in short: **each piece of Dwell exists somewhere. The combination we searched for did not turn up.** Dwell's defensible novelty is in (a) the input modality (an interior phone walkthrough fused with public geodata), (b) joint per-room outputs for three quantities, each with its own coverage-validated interval, and (c) the validation protocol. Novelty does not lie in any single method.

### Contribution 1: inferring hidden envelope properties from partial phone scans plus building metadata, with sensitivity propagation

- **What already exists.**
  - *Image → envelope parameter → physics* is well established at building and urban scale from exterior imagery. Examples: WWR from street view feeding daylight and energy models (Szcześniak et al. 2021; Suppa et al. 2025); building age as a BEM input (Benz et al. 2023); EPC class from street and aerial imagery (Mayer et al. 2022).
  - *Metadata-informed priors on RC parameters* exist for thermostat data (Hossain et al. 2021: priors from homes with similar floor area, age and climate).
  - *Visual material inference for acoustics* exists for interior reverberation (Schissler et al. 2017; Listen2Scene 2024; Image2Reverb 2021; AViTAR 2022).
  - *Variance-based SA* of exactly these parameters (thermal mass, glazing, solar control, ventilation) is standard practice for overheating (Tian 2013; Machard et al. 2023).
  - Commercial phone-LiDAR tools already turn scans into heat-load models for professionals (e.g., autarc, Energy Intelligence; vendor claims).
- **What we did not find.** A system that infers *occupant-invisible* envelope properties (glazing type, frame sealing, wall mass) from *interior* phone walkthrough cues fused with public building metadata, and then propagates the resulting posterior through *both* façade-acoustic and thermal models. We also found no work that classifies single vs. double glazing from ordinary photos (searched; nothing found).
- **What Dwell would add.** A per-apartment, interior-scan-conditioned prior over hidden envelope properties, with Sobol indices that report which hidden property drives each room's uncertainty. Such indices could also say what extra cue to capture.
- **Recommended wording:**
  > "We infer a prior over hidden envelope properties (glazing type, frame airtightness, wall thermal mass) from visual cues in a short interior phone walkthrough combined with public building metadata, and propagate it through façade-acoustic and thermal models using variance-based (Sobol) sensitivity analysis. Prior work infers envelope parameters such as window-to-wall ratio, construction age, or energy class from exterior street-level imagery at the building scale; to our knowledge, and within the literature we searched, we did not find work that conditions such priors on an interior scan or propagates them jointly to acoustic and thermal predictions at room level."

### Contribution 2: hybrid physics + learned residual models with calibrated conformal uncertainty for sun, noise and heat, jointly from a phone scan

- **What already exists.**
  - *Hybrid physics + ML residual models with conformal calibration for indoor temperature* already exist. Von Krannichfeldt, Orehounig & Fink (2025/26) compare five hybrid schemes in a quantile framework calibrated with CQR on a real case study.
  - Conformal intervals for building-simulation outputs exist (Borrotti 2024).
  - Gray-box RC identification (Bacher & Madsen 2011) and physics-constrained deep models (Drgoňa et al. 2021) are mature.
  - ML daylight surrogates are mature (2023 review).
  - Sun-hours products exist at listing scale (Shadowmap / Redfin Sunscore, SunCheck, Localize).
  - Outdoor-to-indoor noise models from noise maps plus façade insulation exist (Locher et al. 2018; Acta Acustica 2025; ISO 12354-3).
- **What we did not find.** A single pipeline that, from one phone walkthrough, gives *per-room* predictions for sun hours, night-time indoor LAeq and summer peak indoor temperature, each with a learned residual on a physics core and **group-conditional (Mondrian) coverage checked against in-home measurements**. None of the commercial sun or noise products we found publishes interval coverage.
- **What Dwell would add.** Joint, per-room, three-quantity prediction with empirically validated coverage, and stratified (Mondrian) coverage by building type or orientation. Do **not** claim hybrid modelling or conformal calibration themselves as new.
- **Recommended wording:**
  > "We combine fast physics models (solar geometry with obstruction ray casting, ISO 12354-3-style façade insulation, and an ISO 13790 5R1C thermal network) with learned residual corrections, and wrap each output in split/CV+ conformal prediction intervals with group-conditional coverage. Hybrid physics–ML models with conformal calibration have previously been demonstrated for building indoor temperature and loads; our contribution is applying this approach jointly to per-room direct-sun hours, night-time indoor noise, and summer peak temperature from a single phone walkthrough, and reporting empirical interval coverage against in-home measurements."

### Contribution 3: a privacy-preserving multi-week in-home sensor validation protocol plus a renter decision study

- **What already exists.**
  - Multi-month, low-cost in-home temperature monitoring is routine (Lomas & Porritt 2017; the 2022 *Sensors* overheating system).
  - Low-cost temperature/RH accuracy has been chamber-tested (Demanega et al. 2021; Salamone et al. 2022).
  - Low-cost MEMS SPL calibration to Class-2 level exists (Mydlarz et al. 2017; SONYC 2019).
  - "No audio, levels only" privacy dates back to NoiseTube (2009) and is used by NoiseCapture.
  - On decisions: noise disclosure changes prices (Pope 2008); sunlight is capitalized into prices (Fleming et al. 2018; Shanghai; Jung et al.); uncertainty displays improve decisions and trust (Fernandes et al. 2018; Joslyn & LeClerc 2012; Zhang et al. 2020).
- **What we did not find.** A protocol that validates *predicted* per-room sun, indoor night noise and peak temperature *simultaneously*, with a single low-cost dB-only + lux + temperature/RH device per room, over several weeks. We also found no renter-facing experiment testing whether *calibrated per-room* predictions of these quantities change apartment choice or trust.
- **What Dwell would add.** A reusable validation protocol with privacy constraints (on-device A-weighted levels, no audio), and a decision study that combines the hedonic evidence with the uncertainty-display literature for rental search.
- **Caveat to state explicitly:** INMP441-class MEMS microphones have ±3 dB sensitivity tolerance and a noise floor of roughly 35 dB (hobbyist project report). Quiet bedrooms at night may sit near or below that floor, so Dwell must report per-unit calibration and a censoring rule for low levels.
- **Recommended wording:**
  > "We contribute a privacy-preserving validation protocol in which a low-cost per-room sensor (illuminance, temperature/humidity, and an on-device A-weighted sound level with no audio retained) is deployed for several weeks to evaluate predicted direct-sun exposure, night-time indoor LAeq, and summer peak temperature together. We also report a renter decision study, building on prior evidence that disclosed noise and sunlight information affects housing prices and that well-designed uncertainty displays improve everyday decisions. Within the literature we searched, we did not find a study that validates all three predicted per-room quantities simultaneously in occupied homes or tests calibrated per-room predictions in rental decision-making."

### Words to avoid

- "First system to show sunlight for home buyers": false (Shadowmap/Redfin Sunscore, Localize, SunCheck).
- "First hybrid physics–ML with conformal uncertainty for buildings": false (Von Krannichfeldt et al. 2025/26; Borrotti 2024).
- "First to infer building envelope properties from images": false (WWR, age and EPC from street view).
- "First" without qualification for anything. Use "to our knowledge, within the literature we searched (searches run 2026-10-24)".

### Closest prior works (ranked)

1. **Von Krannichfeldt, Orehounig, Fink (2025/26)**: hybrid physics–ML plus conformalized quantile regression for indoor temperature (overlaps contribution 2 for heat).
2. **Shadowmap / Redfin Sunscore (2026)**: listing-scale 3D sun simulation for buyers (overlaps the sun product framing).
3. **Locher et al. (2018)** plus **ISO 12354-3** and the **Acta Acustica 2025 outdoor-to-indoor framework**: indoor noise predicted from outdoor maps and façade properties (overlaps the noise physics).
4. **Mayer et al. (2022)** and **Szcześniak et al. (2021)**: hidden or energy-relevant building properties inferred from imagery and fed to physics (overlaps contribution 1, at exterior and building scale).
5. **Hossain, Zhang, Ardakanian (2021)**: metadata-informed priors on gray-box RC parameters across thousands of homes (overlaps the prior-learning idea in contribution 1).

---

## Gaps / not verified

Things we searched for on 2026-10-24 but could not verify or find, so they are left out of the tables above or flagged:

- **Glazing-type classification (single/double/triple) from ordinary photos.** No work found. Only window detection and WWR.
- **An open, long-term, calibrated in-bedroom sound-level dataset.** None found. A seven-day in-home noise pilot (National Children's Study; PubMed 27053775) exists, but we did not find a data release.
- **An open residential indoor-illuminance time-series dataset.** None found, apart from IDEAL's room light sensors. A workplace smartphone-image/lux dataset on Zenodo (PubMed 42631099) was seen but not inspected.
- **Peer-reviewed IEC 61672-style evaluation of the INMP441 specifically.** Not found. Only hobbyist reports and the datasheet. One Arduino-forum report of about 10 dB discrepancy vs. phone apps was not resolved.
- **Authors of the Acta Acustica 2025 outdoor-to-indoor paper.** The page fetch was blocked (HTTP 403), so authors are not listed.
- **Byline of the Toronto night-time noise surface paper (JOEH 2018).** The author list comes from a citing paper. The article page did not show it.
- **Licences:** IDEAL end-user licence terms (not read), ECCC climate data licence name (not confirmed as OGL-Canada), Dryad licence for the ASHRAE DB II, Sounds of Home terms.
- **ISO 13790:2008 current status.** Not checked (ISO 52016-1 is confirmed current as of its 2022 review).
- **Wi-Fi coverage prediction from phone scans (optional Dwell output).** Not searched in depth. No entries included.
- **A road-noise-specific hedonic meta-analysis and a standard road NSDI value.** Not verified. A secondary figure of about 0.2%/dB was seen but not traced to a primary source.
- **Seniguer et al. (smartphone-image illuminance prediction).** Mentioned in a review snippet but not verified.
- **Exact author lists for the Shanghai sunlight study (IJSPM) and the Turin daylight-price study.** Not retrieved. Titles, venues and URLs were verified.
- **Gunay/O'Brien work on ecobee data specifically.** Not found. Their verified work is the 2016 office gray-box paper.
