import { motion } from "framer-motion";

const CreditScoreRing = ({ score = 785 }: { score?: number }) => {
  const maxScore = 900;
  const pct = score / maxScore;
  const circumference = 2 * Math.PI * 45;
  const dashOffset = circumference * (1 - pct);

  return (
    <div className="relative flex items-center justify-center">
      <svg width="100" height="100" viewBox="0 0 100 100" className="-rotate-90">
        <circle
          cx="50" cy="50" r="45"
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth="6"
        />
        <motion.circle
          cx="50" cy="50" r="45"
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 1.5, ease: "easeOut", delay: 0.3 }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <motion.span
          className="font-display text-2xl font-bold text-foreground"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          {score}
        </motion.span>
        <span className="text-[9px] uppercase tracking-wider text-muted-foreground">Score</span>
      </div>
    </div>
  );
};

export default CreditScoreRing;
