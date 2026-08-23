"""Controllers: what each endpoint actually does.

routes/ owns the HTTP contract - path, method, status code, response model and
the dependencies FastAPI must resolve. Everything after that (ownership checks,
orchestration across services, shaping the response) lives here, taking plain
resolved values rather than Request objects.

The split keeps two things separable that otherwise drift together: the API
surface, which is a promise to clients, and the logic behind it, which is free
to change. It also makes a handler testable by calling a function instead of
standing up an ASGI app.

Controllers may call services/, db/ and integrations/. They never import
routes/, and they never touch a Request.
"""
