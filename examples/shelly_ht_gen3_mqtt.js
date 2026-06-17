// Shelly H&T Gen3 -> OnSafe hardware server MQTT example.
// Configure the Shelly device MQTT broker first, then run this script on the device.

let SENSOR_ID = "shelly-ht-001";
let SENSOR_TYPE = "temp_humidity";
let INTERVAL_MS = 60000;

let telemetryTopic = "sensors/" + SENSOR_ID + "/telemetry";
let statusTopic = "sensors/" + SENSOR_ID + "/status";

function publishStatus() {
  if (!MQTT.isConnected()) {
    print("MQTT is not connected");
    return;
  }

  let ok = MQTT.publish(
    statusTopic,
    JSON.stringify({
      sensor_id: SENSOR_ID,
      sensor_type: SENSOR_TYPE,
      is_online: true,
    }),
    1,
    false
  );
  if (!ok) print("status publish failed");
}

function publishTelemetry() {
  if (!MQTT.isConnected()) {
    print("MQTT is not connected");
    return;
  }

  let temp = Shelly.getComponentStatus("temperature:0");
  let humid = Shelly.getComponentStatus("humidity:0");

  if (temp === null || humid === null || temp.tC === null || humid.rh === null) {
    print("temperature or humidity is not available yet");
    return;
  }

  let ok = MQTT.publish(
    telemetryTopic,
    JSON.stringify({
      sensor_id: SENSOR_ID,
      sensor_type: SENSOR_TYPE,
      temp: temp.tC,
      humid: humid.rh,
    }),
    1,
    false
  );
  if (!ok) print("telemetry publish failed");
}

publishStatus();
publishTelemetry();

Timer.set(INTERVAL_MS, true, function () {
  publishStatus();
  publishTelemetry();
});

MQTT.setConnectHandler(function () {
  publishStatus();
  publishTelemetry();
});
