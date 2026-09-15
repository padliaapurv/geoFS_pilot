# Logging setup: human-readable event log (Python logging, console + file)
# kept separate from the per-step numeric telemetry (flat CSV), since they
# serve different consumers (an engineer reading logs vs. a plotting script).

import csv
import logging
import os
from dataclasses import fields, dataclass


def setup_logging(config: dict) -> None:
    log_file = config.get("log_file")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w"))

    logging.basicConfig(
        level=getattr(logging, config.get("level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


@dataclass
class TelemetryRow:
    t_s: float
    north_m: float
    east_m: float
    altitude_m: float
    airspeed_m_s: float
    alpha_deg: float
    beta_deg: float
    roll_deg: float
    pitch_deg: float
    heading_deg: float
    p_deg_s: float
    q_deg_s: float
    r_deg_s: float
    cl: float
    cd: float
    aileron_deg: float
    elevator_deg: float
    rudder_deg: float
    elevator_trim_deg: float
    throttle_fraction: float
    wind_north_m_s: float
    wind_east_m_s: float
    wind_down_m_s: float


class TelemetryLogger:
    def __init__(self, csv_path: str, stride: int = 1):
        self.csv_path = csv_path
        self.stride = max(1, stride)
        self._step_count = 0
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self._file = open(csv_path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=[f.name for f in fields(TelemetryRow)])
        self._writer.writeheader()

    def log(self, row: TelemetryRow) -> None:
        self._step_count += 1
        if self._step_count % self.stride != 0:
            return
        self._writer.writerow({f.name: getattr(row, f.name) for f in fields(TelemetryRow)})

    def close(self) -> None:
        self._file.close()
