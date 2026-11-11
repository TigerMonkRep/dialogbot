---
id: F-VF-04-TESTDEBT
scenario: PC-INV-08
reported_by: verifier
severity: S3
status: new
owner_fix: billing-qa
related: [F-PBQ-02-PC-SUB-06, F-PQ-03-X09]
---

## Kort
tests/qa/test_qa_pd_billing.py::test_pc_inv_08_referral_caps_hold er skrevet før beslutningen om, at henvisningsbonussen først gives efter den henvistes første BETALTE periode, og giver 0 rækker i stedet for 10. Markeret xfail(strict) – skal omskrives med betalte perioder, så loftet (10/md.) stadig er dækket. Ligeledes dokumenterer test_pc_sub_06 (xfail) en forkastet løsning for F-PBQ-02.
