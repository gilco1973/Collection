"""Grounded retrieval: heading-bounded chunks, an embedder protocol, a sqlite vector index and a retriever.

Withholding is never decided here: the index holds every page, and every query passes the caller's
``allowed_paths`` (the same readable view the chat and the API compute) inside the query itself.
"""
