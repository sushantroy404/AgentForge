from fastapi import Request


def c(request: Request):
    return request.app.state.c
