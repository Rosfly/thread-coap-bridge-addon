ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apk add --no-cache \
    bash \
    libcoap \
    tcpdump \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    iputils \
    net-tools \
    iproute2 \
    sqlite \
    libffi-dev \
    openssl-dev \
    gcc \
    musl-dev \
    python3-dev

# Create app directory
WORKDIR /app

# Copy requirements first (better Docker caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code and service definitions
COPY rootfs /

# Make service scripts executable
RUN chmod a+x /etc/services.d/coap-bridge/run && \
    chmod a+x /etc/services.d/coap-bridge/finish

# Set working directory for the app
WORKDIR /app

# Labels for Home Assistant
LABEL \
    io.hass.name="Thread CoAP Bridge" \
    io.hass.description="Bridge CoAP devices on Thread network to MQTT" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.arch="${BUILD_ARCH}"
