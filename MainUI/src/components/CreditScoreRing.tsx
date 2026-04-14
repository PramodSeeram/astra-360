import { motion } from "framer-motion";

const CreditScoreGauge = ({ score = 780 }: { score?: number }) => {
  const minScore = 300;
  const maxScore = 900;
  const pct = (score - minScore) / (maxScore - minScore);
  // Semi-circle: from 180deg to 0deg (left to right)
  const startAngle = 180;
  const endAngle = 180 - pct * 180;
  const r = 80;
  const cx = 100;
  const cy = 95;

  const polarToCart = (angleDeg: number) => ({
    x: cx + r * Math.cos((angleDeg * Math.PI) / 180),
    y: cy - r * Math.sin((angleDeg * Math.PI) / 180),
  });

  const start = polarToCart(startAngle);
  const end = polarToCart(endAngle);
  const largeArc = pct > 0.5 ? 1 : 0;
  const arcPath = `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  const bgEnd = polarToCart(0);
  const bgPath = `M ${start.x} ${start.y} A ${r} ${r} 0 1 1 ${bgEnd.x} ${bgEnd.y}`;

  // Dot position at the end of the arc
  const dot = polarToCart(endAngle);

  return (
    <div className="relative flex flex-col items-center">
      <svg width="200" height="120" viewBox="0 0 200 120">
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        <motion.path
          d={arcPath}
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth="8"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.5, ease: "easeOut", delay: 0.3 }}
        />
        {/* Neon dot at end */}
        <motion.circle
          cx={dot.x}
          cy={dot.y}
          r="6"
          fill="hsl(var(--primary))"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5 }}
        />
        {/* Labels */}
        <text x="20" y="110" fill="hsl(var(--muted-foreground))" fontSize="10" fontFamily="var(--font-display)">
          {minScore}
        </text>
        <text x="170" y="110" fill="hsl(var(--muted-foreground))" fontSize="10" fontFamily="var(--font-display)">
          {maxScore}
        </text>
      </svg>
      <motion.div
        className="absolute bottom-2 flex flex-col items-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
      >
        <span className="font-display text-4xl font-bold text-foreground">{score}</span>
        <span className="text-xs font-medium text-primary mt-0.5">Excellent</span>
      </motion.div>
    </div>
  );
};

export default CreditScoreGauge;
