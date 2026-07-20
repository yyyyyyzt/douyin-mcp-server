/**
 * 轻量 Markdown → rich-text nodes（覆盖标题 / 列表 / 粗体 / 换行）。
 * 不引入重依赖；复杂语法原样展示。
 */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function inlineFormat(text) {
  let s = escapeHtml(text);
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  return s;
}

function mdToHtml(md) {
  const lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  let inUl = false;
  let inOl = false;

  const closeLists = () => {
    if (inUl) {
      html.push('</ul>');
      inUl = false;
    }
    if (inOl) {
      html.push('</ol>');
      inOl = false;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      closeLists();
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.+)$/);
    if (h) {
      closeLists();
      const level = h[1].length;
      html.push(`<h${level}>${inlineFormat(h[2])}</h${level}>`);
      continue;
    }
    const ul = line.match(/^[-*+]\s+(.+)$/);
    if (ul) {
      if (inOl) {
        html.push('</ol>');
        inOl = false;
      }
      if (!inUl) {
        html.push('<ul>');
        inUl = true;
      }
      html.push(`<li>${inlineFormat(ul[1])}</li>`);
      continue;
    }
    const ol = line.match(/^\d+\.\s+(.+)$/);
    if (ol) {
      if (inUl) {
        html.push('</ul>');
        inUl = false;
      }
      if (!inOl) {
        html.push('<ol>');
        inOl = true;
      }
      html.push(`<li>${inlineFormat(ol[1])}</li>`);
      continue;
    }
    closeLists();
    html.push(`<p>${inlineFormat(line)}</p>`);
  }
  closeLists();
  return html.join('') || '<p></p>';
}

function mdToNodes(md) {
  // 微信 rich-text 支持 nodes 为 HTML 字符串
  return mdToHtml(md);
}

function mdExcerpt(md, maxLen = 80) {
  const plain = String(md || '')
    .replace(/[#*_`>\-]/g, '')
    .replace(/\n+/g, ' ')
    .trim();
  if (plain.length <= maxLen) return plain;
  return plain.slice(0, maxLen) + '…';
}

module.exports = { mdToHtml, mdToNodes, mdExcerpt };
