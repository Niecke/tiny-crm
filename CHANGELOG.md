# Changelog

## [0.2.0](https://github.com/Niecke/tiny-crm/compare/v0.1.0...v0.2.0) (2026-10-08)


### Features

* add a draft stage before lead in the deal pipeline ([#265](https://github.com/Niecke/tiny-crm/issues/265)) ([2cabae5](https://github.com/Niecke/tiny-crm/commit/2cabae5a70a24b29c0b0b3cd3b6b4655b5035b06))
* add app-wide search across all tables ([#243](https://github.com/Niecke/tiny-crm/issues/243)) ([d2197eb](https://github.com/Niecke/tiny-crm/commit/d2197ebfa4081dcc04f011b85e4d32156d31ef1d))
* add change history and optimistic concurrency control ([#142](https://github.com/Niecke/tiny-crm/issues/142)) ([#268](https://github.com/Niecke/tiny-crm/issues/268)) ([d93492d](https://github.com/Niecke/tiny-crm/commit/d93492d2acfbd422c74abc4f0d2554cb72b86db0))
* add Content-Security-Policy and security headers ([#235](https://github.com/Niecke/tiny-crm/issues/235)) ([833d375](https://github.com/Niecke/tiny-crm/commit/833d3759d9ca52d2e3cc255d5c5b90308627fcb5))
* add GET /metrics/dashboard with phase 0 and phase 1 numbers ([#138](https://github.com/Niecke/tiny-crm/issues/138)) ([#249](https://github.com/Niecke/tiny-crm/issues/249)) ([5aa993d](https://github.com/Niecke/tiny-crm/commit/5aa993d62f26cc50bf8c238250f8f731dca6c04c))
* add per-account login backoff and reset-mail cooldown ([#246](https://github.com/Niecke/tiny-crm/issues/246)) ([bc03a90](https://github.com/Niecke/tiny-crm/commit/bc03a90a1e7a34d36bc99cb5374e94be50f56c23))
* add won/lost outcomes and tasks completed to the dashboard numbers ([#138](https://github.com/Niecke/tiny-crm/issues/138)) ([#272](https://github.com/Niecke/tiny-crm/issues/272)) ([b691211](https://github.com/Niecke/tiny-crm/commit/b6912118d22665b1601875dfcae9143a2689b298))
* archive instead of delete ([#140](https://github.com/Niecke/tiny-crm/issues/140)) ([#258](https://github.com/Niecke/tiny-crm/issues/258)) ([4739353](https://github.com/Niecke/tiny-crm/commit/4739353f0ccc859803fa31131ca91392536932f1))
* fix release.yml ([#233](https://github.com/Niecke/tiny-crm/issues/233)) ([a3bd300](https://github.com/Niecke/tiny-crm/commit/a3bd30017d976919cd72497eda06b5ee71bdeaf7)), closes [#114](https://github.com/Niecke/tiny-crm/issues/114)
* **frontend:** show the number of due tasks in the nav ([#260](https://github.com/Niecke/tiny-crm/issues/260)) ([e6f87bb](https://github.com/Niecke/tiny-crm/commit/e6f87bb2839bd1693697e4ba6463754966935515))
* headline numbers and new deals per week on the dashboard ([#138](https://github.com/Niecke/tiny-crm/issues/138)) ([#261](https://github.com/Niecke/tiny-crm/issues/261)) ([202bed9](https://github.com/Niecke/tiny-crm/commit/202bed990852ef10e177ba7a7b8bcf9c192e1cdd))
* list deals past their expected close date in the morning briefing ([#117](https://github.com/Niecke/tiny-crm/issues/117)) ([#267](https://github.com/Niecke/tiny-crm/issues/267)) ([6a368f8](https://github.com/Niecke/tiny-crm/commit/6a368f83fe45b6cf0117d8c3c95bcfe57a8450ce))


### Bug Fixes

* **deps:** update caddy:alpine docker digest to 881bbc6 ([#231](https://github.com/Niecke/tiny-crm/issues/231)) ([81f0f82](https://github.com/Niecke/tiny-crm/commit/81f0f8237461fbdf616e0d8bbe59875d7db847da))
* **deps:** update caddy:alpine docker digest to d44355d ([#242](https://github.com/Niecke/tiny-crm/issues/242)) ([7392984](https://github.com/Niecke/tiny-crm/commit/73929846575139c369253bf02359351301736b04))
* **deps:** update caddy:alpine docker digest to d8542f4 ([#251](https://github.com/Niecke/tiny-crm/issues/251)) ([f5eccd1](https://github.com/Niecke/tiny-crm/commit/f5eccd15e78dbcdf7ef9f55ddbd89b2a714dd62d))
* **deps:** update docker.io/library/python:3.14-slim docker digest to c3e521d ([#227](https://github.com/Niecke/tiny-crm/issues/227)) ([fba9240](https://github.com/Niecke/tiny-crm/commit/fba924062768449b6ae2921b44a4fd8557a35b7c))
* **deps:** update docker.io/library/python:3.14-slim docker digest to f85c569 ([#252](https://github.com/Niecke/tiny-crm/issues/252)) ([a532a75](https://github.com/Niecke/tiny-crm/commit/a532a75b4da2630c1a51b55b026b42013f55edf3))
* **deps:** update ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie docker digest to 3e89ea9 ([#244](https://github.com/Niecke/tiny-crm/issues/244)) ([9f9c4bc](https://github.com/Niecke/tiny-crm/commit/9f9c4bc1579e733cf6f3cd3a386e067670abcb8d))
* **frontend:** highlight today's date in calendar date picker ([#263](https://github.com/Niecke/tiny-crm/issues/263)) ([07c1064](https://github.com/Niecke/tiny-crm/commit/07c10642a809eaf91071b135830cef1e02fcd41e)), closes [#256](https://github.com/Niecke/tiny-crm/issues/256)
* offer 50 records in picker dropdowns and say when more exist ([#270](https://github.com/Niecke/tiny-crm/issues/270)) ([a656fd3](https://github.com/Niecke/tiny-crm/commit/a656fd36942e9a3d473efecfdeef3fb05bf2b3b7))

## 0.1.0 (2026-10-01)


### Features

* add event as an interaction kind ([#209](https://github.com/Niecke/tiny-crm/issues/209)) ([71459ae](https://github.com/Niecke/tiny-crm/commit/71459aed0ac8c66a1cc0d75d033148d9de0f48a2))
* add inbox and a PWA for sharing on android ([#175](https://github.com/Niecke/tiny-crm/issues/175)) ([afdd17b](https://github.com/Niecke/tiny-crm/commit/afdd17bfeab002b7929e2c9e2b049de7e5eda995))
* add React Aria with OpenAPI specs and the organization tab ([#172](https://github.com/Niecke/tiny-crm/issues/172)) ([9f5fb79](https://github.com/Niecke/tiny-crm/commit/9f5fb790053369af1ecf9bed8aa2be5e8cb4f413))
* add staging ([#168](https://github.com/Niecke/tiny-crm/issues/168)) ([7054a6d](https://github.com/Niecke/tiny-crm/commit/7054a6d65af2e4f40848e137b106b6ec1be07a23))
* add version to system tab ([#177](https://github.com/Niecke/tiny-crm/issues/177)) ([9f42918](https://github.com/Niecke/tiny-crm/commit/9f42918be70ad78fee1daea71268af2522a1eff3))
* adding forntend tests for react ([#215](https://github.com/Niecke/tiny-crm/issues/215)) ([2ad401c](https://github.com/Niecke/tiny-crm/commit/2ad401c0fab8d8c7cde20e0f3661ed3df75b5ea0))
* adding the dashboard [#138](https://github.com/Niecke/tiny-crm/issues/138) [#122](https://github.com/Niecke/tiny-crm/issues/122) ([#173](https://github.com/Niecke/tiny-crm/issues/173)) ([eb13f9a](https://github.com/Niecke/tiny-crm/commit/eb13f9ad9fa052eb2770735b840d4a61bee37797))
* Disable the public API docs in production ([#200](https://github.com/Niecke/tiny-crm/issues/200)) ([1cdfcb1](https://github.com/Niecke/tiny-crm/commit/1cdfcb19082728974941da41b35ca44cfd90f8fd))
* fix broken password change ([#205](https://github.com/Niecke/tiny-crm/issues/205)) ([d172a95](https://github.com/Niecke/tiny-crm/commit/d172a959beb71ba57b77ef13fda68a7a962d8bc9))
* Freeze the Flutter app ([#212](https://github.com/Niecke/tiny-crm/issues/212)) ([0298ada](https://github.com/Niecke/tiny-crm/commit/0298ada6571617c655a80e5d3f316d3ab668fa1b)), closes [#123](https://github.com/Niecke/tiny-crm/issues/123)
* **frontend-next:** account page and password change ([#179](https://github.com/Niecke/tiny-crm/issues/179)) ([3e80624](https://github.com/Niecke/tiny-crm/commit/3e8062478407b0069c19fc0a52dc5ef5bb2aa659))
* **frontend-next:** contacts list, record page and form ([#181](https://github.com/Niecke/tiny-crm/issues/181)) ([06b0562](https://github.com/Niecke/tiny-crm/commit/06b0562e488dad9672c5f6e20ef209c57ccc4617))
* **frontend-next:** deals — pipeline board, list, record page, form ([#189](https://github.com/Niecke/tiny-crm/issues/189)) ([2bc691a](https://github.com/Niecke/tiny-crm/commit/2bc691a177c720aa0e88c8283e0643f5cf0375f3))
* **frontend-next:** documents — grid, upload, viewer, record tabs ([#187](https://github.com/Niecke/tiny-crm/issues/187)) ([346a4f6](https://github.com/Niecke/tiny-crm/commit/346a4f632cf2b941544adba0148d82eb1880cbef))
* **frontend-next:** interactions — planned, log, form and record tabs ([#185](https://github.com/Niecke/tiny-crm/issues/185)) ([dbba414](https://github.com/Niecke/tiny-crm/commit/dbba41427d9d76aeb187c778ee88a0e85ccf098e))
* **frontend-next:** projects with list-based linked records ([#191](https://github.com/Niecke/tiny-crm/issues/191)) ([ea6767a](https://github.com/Niecke/tiny-crm/commit/ea6767af8d327804b90f470b528234727050ed14))
* **frontend-next:** tasks with priority at a glance ([#183](https://github.com/Niecke/tiny-crm/issues/183)) ([2781192](https://github.com/Niecke/tiny-crm/commit/27811922b016a234b3d95d94dc96bbcd992a2d2c))
* **frontend-next:** watches — sources, sweeps and the due badge ([#193](https://github.com/Niecke/tiny-crm/issues/193)) ([cf2e197](https://github.com/Niecke/tiny-crm/commit/cf2e19784b975f25f745fe5f9263f2501675819b))
* interaction kind event ([#214](https://github.com/Niecke/tiny-crm/issues/214)) ([08a115e](https://github.com/Niecke/tiny-crm/commit/08a115e44195b403013e896e64cb18ce3bf66398))
* react skeleton with login ([#170](https://github.com/Niecke/tiny-crm/issues/170)) ([2926776](https://github.com/Niecke/tiny-crm/commit/292677622442ac0a04b6a8048c2cc5808ee73e21))
* ReDoS in capture parser edge trimming (CodeQL py/polynomial-redos) ([#218](https://github.com/Niecke/tiny-crm/issues/218)) ([c2335e9](https://github.com/Niecke/tiny-crm/commit/c2335e9a5b495e59584664b644e68ed90bfe0602)), closes [#210](https://github.com/Niecke/tiny-crm/issues/210)
* release pipeline ([#163](https://github.com/Niecke/tiny-crm/issues/163)) ([6661eb4](https://github.com/Niecke/tiny-crm/commit/6661eb4be0b0c27787ad2c627e20a75c5829765a))
* system tab ([#176](https://github.com/Niecke/tiny-crm/issues/176)) ([a40e451](https://github.com/Niecke/tiny-crm/commit/a40e451ba966263045b6e619f7a5a88761ec994d))
* T23 · Password reset, and the mail sender it needs ([#202](https://github.com/Niecke/tiny-crm/issues/202)) ([bf90dd2](https://github.com/Niecke/tiny-crm/commit/bf90dd253265cda33a3c96c6252a4fb21c6ff48d))
* T24 · Short-lived tokens with refresh, and a real logout ([#208](https://github.com/Niecke/tiny-crm/issues/208)) ([e324b00](https://github.com/Niecke/tiny-crm/commit/e324b00176d37f230085bcef5d516c6d5078285b)), closes [#133](https://github.com/Niecke/tiny-crm/issues/133)
* T42 · Deal stage timestamps and stage-change events ([#217](https://github.com/Niecke/tiny-crm/issues/217)) ([4ecac60](https://github.com/Niecke/tiny-crm/commit/4ecac60eae8790c2185f4af1ed3d163a6f977d40)), closes [#115](https://github.com/Niecke/tiny-crm/issues/115)
* T43 · Deals with no next step, in the morning briefing ([#219](https://github.com/Niecke/tiny-crm/issues/219)) ([337dca3](https://github.com/Niecke/tiny-crm/commit/337dca3f4ff5c5ec8ddc311a31316325a41c43e8)), closes [#116](https://github.com/Niecke/tiny-crm/issues/116)


### Bug Fixes

* **deps:** update docker.io/library/python:3.14-slim docker digest to 51dafde ([#174](https://github.com/Niecke/tiny-crm/issues/174)) ([b45a30d](https://github.com/Niecke/tiny-crm/commit/b45a30d2d4de174b5fe7ddd75982726cc93683dc))
* **deps:** update docker.io/library/python:3.14-slim docker digest to caaf356 ([#158](https://github.com/Niecke/tiny-crm/issues/158)) ([3984d89](https://github.com/Niecke/tiny-crm/commit/3984d8995a0eba13dbccb92f83dd0059e8276bc8))
* **deps:** update ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie docker digest to 00c63b2 ([#195](https://github.com/Niecke/tiny-crm/issues/195)) ([7cb948a](https://github.com/Niecke/tiny-crm/commit/7cb948a84df317642fa8ce881f39e9c9bebdc575))
* **deps:** update ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie docker digest to 99bc64e ([#196](https://github.com/Niecke/tiny-crm/issues/196)) ([6db4123](https://github.com/Niecke/tiny-crm/commit/6db4123ac2a6576a4942dceb6b007232c203d45b))

## Changelog
