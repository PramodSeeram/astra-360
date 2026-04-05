import { Shield } from "lucide-react";

const AstraLogo = ({ size = 48 }: { size?: number }) => (
  <div className="relative inline-flex items-center justify-center">
    <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl" />
    <div className="relative flex items-center justify-center rounded-2xl neu-raised p-3">
      <Shield size={size} className="text-primary" strokeWidth={1.5} />
      <svg
        className="absolute text-primary"
        width={size * 0.35}
        height={size * 0.35}
        viewBox="0 0 24 24"
        fill="currentColor"
      >
        <polygon points="12,2 15,9 22,9 16.5,14 18.5,21 12,17 5.5,21 7.5,14 2,9 9,9" />
      </svg>
    </div>
  </div>
);

export default AstraLogo;
