# Architecture

Product Launch Factory coordinates independently versioned factories. It freezes the owner's brief and evidence, asks Publishing House for reviewed campaign copy, renders that copy as a static landing page, sends the page through WebOps, and hands the verified page screenshots and campaign facts to VideoOps. Software Factory's portable verifier accepts software evidence when that input type is selected. An existing product can instead provide a WebOps evidence package; this does not pretend a new software build happened.

Each handoff names its exact input hashes, child factory revision, child run, output inventory and remaining review obligations. Completed stages can be reused only while those bytes still match. A changed input invalidates downstream work and any launch approval. Failed child stages remain visible and resumable where the child supports recovery. A non-resumable video attempt is preserved before a new attempt starts.

The launch package collects the article, newsletter, three social posts, landing site, video and their evidence. Human approval is tied to the package hash. Approval records local review; this repository has no deployment command. Technical video checks do not establish listening or editorial approval.

The read-only visual floor displays real state, handoffs and output previews. It does not simulate progress. Credentials stay in ignored runtime homes and never enter the public package. Child tools execute only trusted pinned factory code; source files and model output are data.
