FROM python:3.12-slim

# Unbuffered output so the pipeline's progress log appears as it runs, and no
# .pyc files left behind in the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8

WORKDIR /v1

# Dependencies sit in their own layer, so editing anything below does not
# reinstall them.
COPY src/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The package itself, owned by the unprivileged user that runs it.
RUN useradd -m -u 1000 lrasgen
COPY --chown=lrasgen:lrasgen . /v1

USER lrasgen

CMD ["bash"]
