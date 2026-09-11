const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');

const host = process.argv[2] || 'saturn.picoctf.net';
const port = Number(process.argv[3] || 52430);
// The checker uses the magnitude of the output rotation count.
const ratio = 9359n;
const runId = new Date().toISOString().replace(/[:.]/g, '-');
let pending = '';
let transcript = '';
let foundFlag = false;
const socket = net.createConnection({ host, port });
socket.setEncoding('utf8');
socket.setTimeout(15000);
socket.on('data', (chunk) => {
  process.stdout.write(chunk);
  transcript += chunk;
  pending += chunk;
  const flag = transcript.match(/picoCTF\{[^}\r\n]+\}/);
  if (flag) {
    foundFlag = true;
    fs.writeFileSync(path.join(__dirname, 'flag.txt'), flag[0] + '\n');
    socket.end();
    return;
  }
  if (!pending.includes('Answer>')) return;
  const question = pending.match(/input to the machine is\s+(-?\d+)/i);
  if (!question) {
    socket.destroy(new Error('Unrecognized checker prompt'));
    return;
  }
  const answer = (BigInt(question[1]) * ratio).toString();
  process.stdout.write(answer + '\n');
  transcript += answer + '\n';
  pending = '';
  socket.write(answer + '\n');
});
socket.on('timeout', () => socket.destroy(new Error('Checker timed out')));
socket.on('error', (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
socket.on('close', () => {
  fs.writeFileSync(path.join(__dirname, `checker-${runId}.txt`), transcript);
  if (!foundFlag) process.exitCode = 1;
});
