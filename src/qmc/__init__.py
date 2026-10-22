"""Pure-Python engine for quantum-seeded Monte Carlo option pricing.

Nothing in this package talks to AWS. Handlers in ``src/handlers`` wire it to Lambda, SQS and DynamoDB.
"""

ALGO_VERSION = "qmc-v1"
"""Label for the exact numerical recipe (seed derivation, random generator, normal-number step,
summation order). Stored with every job; any change to the numbers must bump it."""
