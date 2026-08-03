# InfluxDB downsampling (bucket + tasks)

The `home_assistant` bucket holds 30 days of raw data (set at chart bootstrap
via `adminUser.retention_policy`). Long-term history lives in
`home_assistant_long` (infinite retention), fed by two hourly tasks defined in
`downsample-template.yml` and applied as an InfluxDB **stack** — re-applying
the template updates the tasks in place instead of duplicating them.

Everything runs through the pod's bundled `influx` CLI; no local tooling needed.

## One-time setup (after HA has been writing for ~30 min)

```bash
TOKEN=$(kubectl -n monitoring get secret influxdb-auth -o jsonpath='{.data.admin-token}' | base64 -d)

# 1. Verify what measurement names actually arrived (expect W, kWh, V, A, °C).
#    Adjust the filters in downsample-template.yml if they differ.
kubectl -n monitoring exec influxdb-influxdb2-0 -- influx query -o home -t "$TOKEN" \
  'import "influxdata/influxdb/schema" schema.measurements(bucket: "home_assistant")'

# 2. Create the stack (ONCE - already done 2026-08-03, stack ID 111dadb5ef15d000)
kubectl -n monitoring exec influxdb-influxdb2-0 -- influx stacks init -o home -t "$TOKEN" \
  --stack-name ha-downsample

# 3. Apply the template to the stack (repeat this step for every future edit)
kubectl -n monitoring cp downsample-template.yml influxdb-influxdb2-0:/tmp/downsample-template.yml
kubectl -n monitoring exec influxdb-influxdb2-0 -- influx apply -o home -t "$TOKEN" \
  --stack-id 111dadb5ef15d000 -f /tmp/downsample-template.yml --force yes
```

Applied 2026-08-03: bucket + both tasks active. Verified measurements arriving
from HA: `W`, `V`, `A`, `°C`, `Wh` (Shelly Gen2 energy is Wh, not kWh - the
energy task filter covers both; Growatt kWh entities also match).

Find the stack ID again later with:
`kubectl -n monitoring exec influxdb-influxdb2-0 -- influx stacks -o home -t "$TOKEN"`

## Verify

```bash
# Tasks registered and active
kubectl -n monitoring exec influxdb-influxdb2-0 -- influx task list -o home -t "$TOKEN"

# After 1-2 hours: downsampled points landing
kubectl -n monitoring exec influxdb-influxdb2-0 -- influx query -o home -t "$TOKEN" \
  'from(bucket: "home_assistant_long") |> range(start: -3h) |> count()'
```

Task run failures also surface in Grafana via the scraped `task_scheduler_*` /
`task_executor_*` metrics (ServiceMonitor in ../service-monitors/).

## Notes

- `fn: mean` for instantaneous readings (W/V/A/°C); `fn: last` for cumulative
  kWh counters — mean of a monotonic counter is meaningless.
- `offset: 5m` lets late writes land before the window is aggregated.
- Grafana panels for long ranges should query `home_assistant_long`;
  `home_assistant` only covers the trailing 30 days.
