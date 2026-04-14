const AstraLogo = ({ size = 48 }: { size?: number }) => (
  <div className="relative inline-flex items-center justify-center">
    <div className="absolute inset-0 rounded-full bg-primary/20 blur-2xl" style={{ width: size * 1.5, height: size * 1.5 }} />
    <img 
      src="/astra360_logo.svg" 
      alt="Astra 360 Logo" 
      style={{ 
        width: size * 1.5, 
        height: size * 1.5, 
        objectFit: 'contain', 
        mixBlendMode: 'screen',
        position: 'relative',
        zIndex: 10
      }} 
    />
  </div>
);

export default AstraLogo;
