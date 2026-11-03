const foundations = [
  ["Python workspace", "weft、weft-worker 与 weft-sdk 可独立安装"],
  ["Frontend toolchain", "React 18、TypeScript strict 与 Vite 已配置"],
  ["Verification", "单元测试、集成测试与 CI 使用统一命令"],
];

export function App() {
  return (
    <main className="app-shell">
      <header className="brand-bar">
        <span className="brand-mark" aria-hidden="true">
          W
        </span>
        <span>Weft</span>
        <span className="version">T0.1</span>
      </header>
      <section className="foundation-panel">
        <p className="eyebrow">LOCAL-FIRST WORKFLOWS</p>
        <h1>开发基础已就绪</h1>
        <p className="intro">
          表格数据流、Excel 实时联动与沙箱化 Agent 将从这里开始编织。
        </p>
        <div className="foundation-grid">
          {foundations.map(([title, description]) => (
            <article key={title}>
              <span className="status-dot" aria-hidden="true" />
              <h2>{title}</h2>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
