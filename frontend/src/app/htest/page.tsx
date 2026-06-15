"use client";
import { useState } from "react";

export default function HTest() {
  const [n, setN] = useState(0);
  return (
    <button
      id="htest-btn"
      onClick={() => setN((v) => v + 1)}
      style={{ padding: 40, fontSize: 32 }}
    >
      count {n}
    </button>
  );
}
