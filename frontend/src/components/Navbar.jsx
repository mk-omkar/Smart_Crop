export default function Navbar() {
  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <a href="#home" className="brand" aria-label="Smart Crop Advisor, home">
          <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path
              fill="currentColor"
              d="M20 4C10 4 4 9 4 16c0 1.5.4 2.8 1 4 1.2-4 4-7 8-9-3 3-5 6-5.7 9.6.6.3 1.3.4 2 .4 7 0 11-6 11-14 0-1-.1-1.9-.3-3z"
            />
          </svg>
          <span>Smart Crop Advisor</span>
        </a>
        <nav aria-label="Main">
          <a href="#home">Home</a>
          <a href="#about">About</a>
        </nav>
      </div>
    </header>
  );
}
