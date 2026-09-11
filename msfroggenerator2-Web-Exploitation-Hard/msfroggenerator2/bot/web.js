import { createServer } from 'http';
import { spawn } from 'child_process';

let running = false;

createServer((req, res) => {
    const { url } = Object.fromEntries(new URL(`http://${req.headers.host}${req.url}`).searchParams);
    res.writeHead(200);
    if (!url) return res.end('Invalid request');
    if (running) return res.end('Already running!');
    (async () => {
        running = true;
        console.log('Starting...');
        const proc = spawn('node', ['bot.js', url], {
            stdio: ['inherit', 'inherit', 'inherit']
        });
        await new Promise(resolve => proc.on('exit', resolve));
        console.log('Exited');
        running = false;
    })();
    res.end('Sent!');
}).listen(8080);