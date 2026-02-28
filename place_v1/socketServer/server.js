import express from "express";
import {
  ApiGatewayManagementApiClient,
  PostToConnectionCommand,
} from "@aws-sdk/client-apigatewaymanagementapi";
var app = express();
const client = new ApiGatewayManagementApiClient({
  endpoint:
    "https://3naz13dlch.execute-api.us-east-1.amazonaws.com/production/",
  region: "us-east-1",
});

var dim = 250; // note: this is not the right dimensions!!
// x * y * (3 bytes of colors)
const board = new Uint8Array(dim * dim * 3);
board.fill(255);
let connectionIds = new Set();

// History will be saved as the form [connectionId, data in base64] for every entry
let history = [];

app.use(express.raw({ type: "application/octet-stream", limit: "1mb" }));

app.listen(8081, function () {
  console.log("App listening on port 8081");
});

async function sendBoard(connectionId) {
  const buffer = board;
  let offset = 0;
  while (offset < buffer.length) {
    const end = Math.min(offset + 28000, buffer.length);
    const chunk = buffer.slice(offset, end);

    await sendData(connectionId, chunk);
    offset = end;
  }

  console.log("Connected", connectionId);
}

app.post("/connect/:connectionId", async (req, res) => {
  connectionIds.add(req.params.connectionId);
  res.status(200).send({
    status: "Connection Added",
    dim: dim,
  });
  await sendBoard(req.params.connectionId);
});

app.delete("/disconnect/:connectionId", (req, res) => {
  let id = req.params.connectionId;
  if (!connectionIds.has(id)) {
    res.status(400).send({
      error: "Connection does not exist",
    });
  } else {
    console.log("Disconnected", id);
    connectionIds.delete(id);
    res.status(200).send({
      status: "Connection removed",
    });
  }
});

app.put("/draw/:connectionId/:dataBase64", async (req, res) => {
  var data_base64 = req.params.dataBase64;
  var connectionId = req.params.connectionId;

  if (!data_base64) {
    return res.status(400).json({
      error: "Invalid undefined data",
    });
  }
  history.push([connectionId, data_base64]);
  const data = unpackBase64(data_base64); // Buffer size 5 bytes x,y,r,g,b

  if (!data || data.length !== 5) {
    return res.status(400).json({
      error: "Invalid data size",
    });
  }
  const x = data[0];
  const y = data[1];
  const r = data[2];
  const g = data[3];
  const b = data[4];

  if (
    x < 0 ||
    x >= dim ||
    y < 0 ||
    y >= dim ||
    r > 255 ||
    r < 0 ||
    g < 0 ||
    g > 255 ||
    b < 0 ||
    b > 255
  ) {
    return res.status(400).json({ error: "Invalid draw" });
  }

  const i = index(x, y);
  board[i] = r;
  board[i + 1] = g;
  board[i + 2] = b;

  const broadcast_msg = pack(x, y, r, g, b);

  const broadcastPromises = [];
  for (const conn of connectionIds) {
    broadcastPromises.push(sendData(conn, broadcast_msg));
  }

  await Promise.all(broadcastPromises);

  res.status(200).send({
    status: "Draw successful",
  });
});

app.get("ping", (req, res) => {
  res.status(200).send("pong");
});

async function sendData(connectionId, bytes) {
  const encoded = Buffer.from(bytes).toString("base64");
  const params = {
    ConnectionId: connectionId,
    Data: encoded,
  };

  try {
    const command = new PostToConnectionCommand(params);
    await client.send(command);
  } catch (error) {
    console.error(`Error sending data to connection ${connectionId}`, error);
    if (error.name === "GoneException") {
      connectionIds.delete(connectionId);
      console.log(`Connection ${connectionId} is gone`);
    }
  }
}

function index(x, y) {
  return (y * dim + x) * 3;
}

function pack(x, y, r, g, b) {
  const buf = new Uint8Array(5);
  buf[0] = x;
  buf[1] = y;
  buf[2] = r;
  buf[4] = g;
  buf[5] = b;
  return buf;
}
function unpackBase64(base64) {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}
