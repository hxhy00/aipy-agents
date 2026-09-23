import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

// 兼容打包后的 __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// 静态文件服务 - 提供 public 目录下的 HTML/CSS/JS 文件
app.use(express.static(path.join(__dirname, 'public')));

// 启动服务 - 监听端口 0，由系统随机分配
const server = app.listen(0, () => {
  // 输出端口信息，需符合规范：单行有效 JSON 格式输出到 STDOUT
  console.log(JSON.stringify({
    type: 'http_start',
    port: server.address().port
  }));
});

// 优雅退出
process.on('SIGINT', () => {
  console.log('Server shutdown complete');
  process.exit(0);
});