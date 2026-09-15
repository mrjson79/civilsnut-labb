FROM --platform=$BUILDPLATFORM golang:1.26.7@sha256:e30143be198ab04cf7ba25fba83ab3a692ca584c994aad0bf131fa0eb32dd8c1 AS build
ENV GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /src
COPY . .
RUN go get golang.org/x/text@v0.39.0 && go mod tidy
RUN go test ./internal/k8sutil/... ./pkg/...
ARG TARGETOS
ARG TARGETARCH
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags='-s -w' -o /out/netbird-operator ./cmd
FROM gcr.io/distroless/static:nonroot@sha256:e2e927ec666bae08560abb3c55d0659eceabb657f56b6782ab500a9fc7f555e3
LABEL org.opencontainers.image.source="https://github.com/mrjson79/civilsnut-labb" \
      org.opencontainers.image.version="0.8.0-civilsnut.1" \
      org.opencontainers.image.revision="41d995671f55d790a4f4e1c37da8c9e41a36abee"
COPY --from=build /out/netbird-operator /usr/local/bin/netbird-operator
USER 65532:65532
ENTRYPOINT ["netbird-operator"]
