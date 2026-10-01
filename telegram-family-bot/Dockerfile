FROM python:3.11-alpine

ARG BUILD_VERSION
ARG BUILD_ARCH

ENV TELEGRAM_FAMILY_ASSISTANT_VERSION="${BUILD_VERSION}"

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache bash ca-certificates tzdata

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app

RUN python3 -m unittest discover -s tests -v \
    && chmod +x /app/run.sh

CMD ["/bin/bash", "/app/run.sh"]
