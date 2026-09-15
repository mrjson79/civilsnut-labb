FROM --platform=$BUILDPLATFORM golang:1.26.7@sha256:e30143be198ab04cf7ba25fba83ab3a692ca584c994aad0bf131fa0eb32dd8c1 AS build
ENV GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /src
COPY . .
RUN go get google.golang.org/grpc@v1.83.2 && go mod tidy
ARG TARGETOS
ARG TARGETARCH
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -tags load_wgnt_from_rsrc -ldflags='-s -w -X github.com/netbirdio/netbird/version.version=0.78.2-civilsnut.1' -o /out/netbird ./client
RUN CGO_ENABLED=1 go test -tags devcert ./shared/management/client ./shared/signal/client
FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN apk add --no-cache bash ca-certificates ip6tables iproute2 iptables libcrypto3=3.5.8-r0 libssl3=3.5.8-r0
LABEL org.opencontainers.image.source="https://github.com/mrjson79/civilsnut-labb" \
      org.opencontainers.image.version="0.78.2-civilsnut.1" \
      org.opencontainers.image.revision="300b6695012158bdede367738a0389a25d83cf04"
COPY --from=build /out/netbird /usr/local/bin/netbird
COPY client/netbird-entrypoint.sh /usr/local/bin/netbird-entrypoint.sh
ENV NETBIRD_BIN=/usr/local/bin/netbird NB_LOG_FILE=console NB_DAEMON_ADDR=unix:///var/run/netbird.sock NB_ENABLE_CAPTURE=false NB_ENTRYPOINT_SERVICE_TIMEOUT=30
ENTRYPOINT ["/usr/local/bin/netbird-entrypoint.sh"]
