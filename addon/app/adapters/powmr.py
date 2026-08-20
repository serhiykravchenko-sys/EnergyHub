import json
import subprocess
import threading
import time

try:
    import serial
except ModuleNotFoundError:  # Allows protocol unit tests without pyserial.
    serial = None


class ModbusReadError(Exception):
    """Base class for bounded read-only Modbus failures."""


class ModbusTimeoutError(ModbusReadError):
    pass


class ModbusCrcError(ModbusReadError):
    pass


class ModbusMalformedResponseError(ModbusReadError):
    pass


class ModbusUnsupportedError(ModbusReadError):
    pass


class ModbusExceptionResponseError(ModbusReadError):
    pass


class ModbusInvalidValueError(ModbusReadError):
    pass


def modbus_crc(data):
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc


def build_pv2_request():
    frame = bytes([
        5,
        0x03,
        0x11,
        0xD3,
        0x00,
        0x02,
    ])
    return frame + modbus_crc(frame).to_bytes(2, "little")


def decode_pv2_response(response, slave=5):
    if len(response) < 5:
        raise ModbusMalformedResponseError(
            f"response too short: {len(response)} bytes"
        )

    received_crc = int.from_bytes(response[-2:], "little")
    expected_crc = modbus_crc(response[:-2])

    if received_crc != expected_crc:
        raise ModbusCrcError(
            f"CRC mismatch: expected {expected_crc:04x}, "
            f"received {received_crc:04x}"
        )

    if response[0] != slave:
        raise ModbusMalformedResponseError(
            f"unexpected slave address: {response[0]}"
        )

    function = response[1]

    if function == 0x83:
        exception_code = response[2]

        if exception_code in {0x01, 0x02}:
            raise ModbusUnsupportedError(
                f"Modbus exception {exception_code}"
            )

        raise ModbusExceptionResponseError(
            f"Modbus exception {exception_code}"
        )

    if function != 0x03:
        raise ModbusMalformedResponseError(
            f"unexpected function: {function}"
        )

    if len(response) != 9 or response[2] != 4:
        raise ModbusMalformedResponseError(
            f"unexpected byte count or length: "
            f"byte_count={response[2]}, length={len(response)}"
        )

    # The installed POW-HVM10.2M returns the bytes inside each 16-bit
    # payload word swapped relative to normal Modbus register order.
    voltage_raw = int.from_bytes(response[3:5], "little")
    power_w = int.from_bytes(response[5:7], "little")
    voltage_v = voltage_raw / 10.0

    if not 0 <= voltage_v <= 600:
        raise ModbusInvalidValueError(
            f"PV2 voltage outside validated range: {voltage_v} V"
        )

    if not 0 <= power_w <= 12000:
        raise ModbusInvalidValueError(
            f"PV2 power outside validated range: {power_w} W"
        )

    return {
        "pv2_input_voltage": voltage_v,
        "pv2_charging_power": power_w,
    }


class PowMrLocalAdapter:
    def __init__(self, options):
        self.serial_port = options["serial_port"]
        self.protocol = options["protocol"]
        self.command = options["command"]
        self._serial_factory = options.get("_serial_factory")

        if self._serial_factory is None:
            if serial is None:
                raise RuntimeError("pyserial is required at runtime")
            self._serial_factory = serial.Serial

        # Only one mpp-solar process may use the serial port at a time.
        self._serial_lock = threading.Lock()

    def _run_command(self, command):
        cmd = [
            "mpp-solar",
            "-p",
            self.serial_port,
            "-P",
            self.protocol,
            "-c",
            command,
            "-o",
            "json",
        ]

        with self._serial_lock:
            output = subprocess.check_output(
                cmd,
                text=True,
                timeout=25,
            )

        return json.loads(output)

    def read_telemetry(self):
        return self._run_command(self.command)

    def read_warnings(self):
        return self._run_command("QPIWS")

    def read_settings(self):
        return self._run_command("QPIRI")

    def read_pv2_telemetry(self):
        request = build_pv2_request()

        with self._serial_lock:
            with self._serial_factory(
                port=self.serial_port,
                baudrate=2400,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=2,
                write_timeout=2,
            ) as connection:
                connection.reset_input_buffer()
                connection.reset_output_buffer()
                written = connection.write(request)

                if written != len(request):
                    raise ModbusTimeoutError(
                        f"expected to write {len(request)} bytes, "
                        f"wrote {written}"
                    )

                connection.flush()

                header = self._read_exact(connection, 3)

                if header[1] & 0x80:
                    response = header + self._read_exact(connection, 2)
                else:
                    response = header + self._read_exact(
                        connection,
                        header[2] + 2,
                    )

        return decode_pv2_response(
            response,
            slave=5,
        )

    @staticmethod
    def _read_exact(connection, size):
        result = bytearray()
        deadline = time.monotonic() + 2.25

        while len(result) < size and time.monotonic() < deadline:
            chunk = connection.read(size - len(result))

            if not chunk:
                break

            result.extend(chunk)

        if len(result) != size:
            raise ModbusTimeoutError(
                f"expected {size} bytes, received {len(result)}"
            )

        return bytes(result)

    def set_output_source_priority(self, command):
        result = self._run_command(command)
        return result.get("pop") == "ACK"

    def set_charger_source_priority(self, command):
        result = self._run_command(command)
        return result.get("pcp") == "ACK"
