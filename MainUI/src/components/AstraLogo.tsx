const AstraLogo = ({ size = 48 }: { size?: number }) => (
  <div className="relative inline-flex items-center justify-center">
    <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl" />
    <div className="relative flex items-center justify-center rounded-2xl neu-raised p-2" style={{ width: size + 16, height: size + 16 }}>
      <img src="/astra360_logo.svg" alt="Astra 360 Logo" style={{ width: size, height: size, objectFit: 'contain' }} />
    </div>
  </div>
);

export default AstraLogo;
