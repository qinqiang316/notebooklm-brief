// Obsidian Web Clipper 同款正文提取：Mozilla Readability(正文) + Turndown(HTML→Markdown)
// 用法：node extract.js <input.html> [output.md]
//   从 input.html 提取正文并转 Markdown；output.md 缺省时输出到 stdout。
// 退出码：0=成功；2=未提取到正文（Readability parse 返回 null）
const fs = require('fs');
const path = require('path');
const { Readability } = require('@mozilla/readability');
const { JSDOM } = require('jsdom');
const TurndownService = require('turndown');

const inputPath = process.argv[2];
const outputPath = process.argv[3] || null;

if (!inputPath) {
  console.error('用法：node extract.js <input.html> [output.md]');
  process.exit(1);
}

const html = fs.readFileSync(inputPath, 'utf-8');
// jsdom 需要 url 做相对链接解析；无法从文件推断时用占位
const dom = new JSDOM(html, { url: 'https://example.com/' });
const article = new Readability(dom.window.document).parse();

if (!article || !article.content) {
  console.error('未提取到正文（Readability parse 返回空）');
  process.exit(2);
}
// 无正文页（404/登录墙/纯导航）Readability 也能提取出少量噪音，按内容长度过滤
if (article.textContent.trim().length < 200) {
  console.error('正文过短（可能为 404/无内容页）');
  process.exit(2);
}

const turndown = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced',
  bulletListMarker: '-',
  hr: '---',
});
// 链接默认转 [text](href)（keep 会保留 <a> 原样，不用）
turndown.addRule('img', {
  filter: 'img',
  replacement: (content, node) => {
    const src = node.getAttribute('src') || '';
    const alt = node.getAttribute('alt') || '';
    return src ? `![${alt}](${src})` : '';
  },
});

let md = '';
if (article.title) {
  md += `# ${article.title}\n\n`;
}
md += turndown.turndown(article.content).trim() + '\n';

if (outputPath) {
  fs.writeFileSync(outputPath, md, 'utf-8');
  console.error(`已写入 ${path.basename(outputPath)} (${md.length} chars)`);
} else {
  process.stdout.write(md);
}
