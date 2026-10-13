// Extruded outline glyphs: actual projected vertices, with a different view for each level.
const glyphs = {
  H: [
    [0, 0],
    [1, 0],
    [1, 2.1],
    [3, 2.1],
    [3, 0],
    [4, 0],
    [4, 5],
    [3, 5],
    [3, 3],
    [1, 3],
    [1, 5],
    [0, 5],
  ],
  A: [
    [0, 5],
    [1.5, 0],
    [2.5, 0],
    [4, 5],
    [3, 5],
    [2.5, 3.5],
    [1.5, 3.5],
    [1, 5],
  ],
  N: [
    [0, 5],
    [0, 0],
    [1, 0],
    [3, 3.3],
    [3, 0],
    [4, 0],
    [4, 5],
    [3, 5],
    [1, 1.7],
    [1, 5],
  ],
  Z: [
    [0, 0],
    [4, 0],
    [4, 1],
    [1.2, 4],
    [4, 4],
    [4, 5],
    [0, 5],
    [0, 4],
    [2.8, 1],
    [0, 1],
  ],
  I: [
    [0, 0],
    [3, 0],
    [3, 1],
    [2, 1],
    [2, 4],
    [3, 4],
    [3, 5],
    [0, 5],
    [0, 4],
    [1, 4],
    [1, 1],
    [0, 1],
  ],
  Y: [
    [0, 0],
    [1.1, 0],
    [2, 1.9],
    [2.9, 0],
    [4, 0],
    [2.5, 3],
    [2.5, 5],
    [1.5, 5],
    [1.5, 3],
  ],
  O: [
    [0, 1],
    [1, 0],
    [3, 0],
    [4, 1],
    [4, 4],
    [3, 5],
    [1, 5],
    [0, 4],
  ],
  U: [
    [0, 0],
    [1, 0],
    [1, 3.8],
    [1.6, 4.2],
    [2.4, 4.2],
    [3, 3.8],
    [3, 0],
    [4, 0],
    [4, 4],
    [3, 5],
    [1, 5],
    [0, 4],
  ],
};
let pose = 0,
  frame = 0;
export function architecture(container, level = 0) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = pose,
    target = [0, 0.65, 1.25, 1.8][level] || 0,
    began = performance.now();
  cancelAnimationFrame(frame);
  function draw(now) {
    const progress = reduced ? 1 : Math.min(1, (now - began) / 750);
    pose = start + (target - start) * (1 - Math.pow(1 - progress, 3));
    const angle = -0.17 + pose * 0.16;
    const project = ([x, y, z]) => {
      const centered = x - 15;
      const xx = centered * Math.cos(angle) - z * Math.sin(angle);
      const zz = centered * Math.sin(angle) + z * Math.cos(angle);
      return [155 + xx * 8 + zz * 3.6, 102 + y * 6.6 - zz * 3.8];
    };
    const points = (vs) =>
      vs
        .map((v) =>
          project(v)
            .map((n) => n.toFixed(2))
            .join(","),
        )
        .join(" ");
    let svg = "";
    for (let x = -1; x <= 32; x += 3)
      svg += `<polyline points="${points([
        [x, 5, 0],
        [x, 5, 13],
      ])}" opacity=".12"/>`;
    for (let z = 0; z <= 13; z += 3)
      svg += `<polyline points="${points([
        [-1, 5, z],
        [32, 5, z],
      ])}" opacity=".12"/>`;
    function word(text, x, z) {
      for (const ch of text) {
        const shape = glyphs[ch];
        const front = shape.map(([a, b]) => [x + a, b, z]);
        const back = shape.map(([a, b]) => [x + a, b, z + 1.4]);
        svg += `<polygon points="${points(back)}" opacity=".35"/>`;
        front.forEach((v, i) => {
          svg += `<polyline points="${points([v, back[i]])}" opacity=".45"/>`;
        });
        svg += `<polygon points="${points(front)}" fill="var(--bg)" fill-opacity=".7"/>`;
        if (ch === "O")
          svg += `<polygon points="${points([
            [x + 1, 1.1, z],
            [x + 3, 1.1, z],
            [x + 3, 3.9, z],
            [x + 1, 3.9, z],
          ])}"/>`;
        if (ch === "A")
          svg += `<polygon points="${points([
            [x + 1.7, 2.6, z],
            [x + 2.3, 2.6, z],
            [x + 2, 1.4, z],
          ])}"/>`;
        x += ch === "I" ? 4 : 5;
      }
    }
    word("HANZHI", 0, 7);
    word("YOU", 13, 0);
    svg += `<polyline points="${points([
      [-1, 5, 0],
      [-1, 5, 13],
      [32, 5, 13],
    ])}" opacity=".35"/>`;
    container.innerHTML = `<svg viewBox="0 0 320 165" role="img" aria-label="Hanzhi YOU — architectural lettering"><g fill="none" stroke="currentColor" stroke-width=".65" stroke-linejoin="round">${svg}</g><text x="300" y="159" text-anchor="end" fill="currentColor" style="font:italic 12px Baskerville,serif;letter-spacing:1px">Hanzhi YOU</text></svg>`;
    if (progress < 1) frame = requestAnimationFrame(draw);
  }
  frame = requestAnimationFrame(draw);
}
