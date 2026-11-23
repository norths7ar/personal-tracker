export function validatePrompt(text: string, required: string[]): string | null {
  const found = new Set<string>();
  const placeholder = /\$(?:\$|([a-z_][a-z0-9_]*)|\{([a-z_][a-z0-9_]*)\})/iy;
  for (let index = text.indexOf("$"); index !== -1; index = text.indexOf("$", index)) {
    placeholder.lastIndex = index;
    const match = placeholder.exec(text);
    if (!match) return "提示词包含无效的 $ 占位符；普通美元符号请写为 $$。";
    const name = match[1] ?? match[2];
    if (name) {
      if (!required.includes(name)) return `不支持占位符：\${${name}}`;
      found.add(name);
    }
    index = placeholder.lastIndex;
  }
  const missing = required.filter((name) => !found.has(name));
  return missing.length
    ? `请保留必填占位符：${missing.map((name) => `\${${name}}`).join("、")}`
    : null;
}
