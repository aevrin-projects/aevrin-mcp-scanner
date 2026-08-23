"""Thin clients for the external services this app talks to (Redis, R2,
Razorpay, GitHub, DefectDojo, DeepSeek, IP geolocation).

Each knows how to speak one protocol and nothing about Aevrin business rules,
which is what makes them swappable and testable in isolation.
"""
