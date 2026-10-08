"""V2 rule/feature-based recommender. No ML, embeddings or LLMs.

Pipeline:  events → profile → candidates → features → weighted score → diversity re-rank → top K
Everything except service.py is pure Python (no database), so each stage is unit-testable
and the offline evaluation reuses exactly the production pipeline.
"""
