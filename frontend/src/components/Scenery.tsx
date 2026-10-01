export function RoadIllustration() {
  return (
    <svg
      className="road-art"
      viewBox="0 0 600 290"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="bus-body" x1="210" y1="100" x2="440" y2="230">
          <stop stopColor="#fff" />
          <stop offset="1" stopColor="#c8cbff" />
        </linearGradient>
      </defs>
      <circle cx="428" cy="86" r="63" fill="white" opacity=".055" />
      <circle cx="428" cy="86" r="92" stroke="white" strokeOpacity=".09" />
      <circle cx="428" cy="86" r="121" stroke="white" strokeOpacity=".06" />
      <path
        d="M-20 241C138 113 291 342 617 86"
        stroke="#b0a6ff"
        strokeWidth="66"
        opacity=".14"
      />
      <path
        d="M-20 241C138 113 291 342 617 86"
        stroke="#d8d2ff"
        strokeDasharray="11 13"
        opacity=".55"
      />
      <path
        d="M411 58V40m-8 9h16M164 124v-12m-6 6h12"
        stroke="#d4d0ff"
        strokeWidth="2"
      />
      <circle cx="503" cy="169" r="4" fill="#b8f1dd" />
      <g transform="translate(112 43) rotate(-8 190 110)">
        <ellipse
          cx="220"
          cy="181"
          rx="139"
          ry="19"
          fill="#181944"
          opacity=".22"
        />
        <path
          d="M87 87q0-22 22-22h183q23 0 29 25l14 71H87Z"
          fill="url(#bus-body)"
        />
        <path d="M96 92q0-16 14-16h176q13 0 18 17l8 30H96Z" fill="#282b64" />
        <path
          d="M111 81h26v37h-26zm34 0h28v37h-28zm36 0h28v37h-28zm36 0h28v37h-28zm37 0h28q10 0 14 14l6 23h-48z"
          fill="#7277b4"
        />
        <path d="M91 132h231l5 18H91" fill="#8176f4" />
        <path d="M234 132h88l5 18h-88" fill="#6353da" />
        <rect x="84" y="150" width="251" height="14" rx="5" fill="#f4f3ff" />
        <circle cx="127" cy="162" r="20" fill="#222445" />
        <circle cx="127" cy="162" r="10" fill="#979bc7" />
        <circle cx="290" cy="162" r="20" fill="#222445" />
        <circle cx="290" cy="162" r="10" fill="#979bc7" />
        <path
          d="M104 138h62"
          stroke="white"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <rect x="313" y="134" width="10" height="6" rx="2" fill="#fff1b8" />
      </g>
      <g transform="translate(426 66)">
        <rect width="109" height="43" rx="12" fill="white" />
        <circle cx="22" cy="22" r="10" fill="#e6f8ef" />
        <path
          d="m18 22 3 3 5-6"
          stroke="#299371"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <text
          x="40"
          y="19"
          fill="#333653"
          fontSize="9"
          fontFamily="Arial"
          fontWeight="bold"
        >
          Less refreshing.
        </text>
        <text x="40" y="31" fill="#82869b" fontSize="8" fontFamily="Arial">
          More going places.
        </text>
      </g>
      <g transform="translate(149 196)">
        <rect width="91" height="34" rx="10" fill="#f6c89c" />
        <path d="M14 10v14m-4-4 4 4 4-4" stroke="#69513d" strokeWidth="1.5" />
        <text
          x="28"
          y="21"
          fill="#69513d"
          fontFamily="Arial"
          fontSize="9"
          fontWeight="bold"
        >
          Your next stop
        </text>
      </g>
    </svg>
  );
}
export function DestinationArt({ type }: { type: "sea" | "hills" | "city" }) {
  return (
    <svg
      viewBox="0 0 360 150"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {type === "sea" ? (
        <>
          <rect width="360" height="150" fill="#fde3c7" />
          <circle cx="272" cy="52" r="28" fill="#eea773" />
          <path d="M0 89q70-13 160 5t200-8v64H0" fill="#92c5c4" />
          <path d="M0 110q83-18 174 6t186-7v41H0" fill="#62a8ae" />
          <path d="M0 134q116-26 360 5v11H0" fill="#f2d7b2" />
          <path
            d="M45 128q9-47-7-68m3 4q-36-17-38 11m38-11q27-28 51-4m-52 5q-4-28-33-29m35 27q22-4 31 19"
            stroke="#426b62"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
          <path d="m173 41 6-4 6 4m8 7 5-3 5 3" stroke="#b28b76" fill="none" />
        </>
      ) : type === "hills" ? (
        <>
          <rect width="360" height="150" fill="#d9ebe1" />
          <circle cx="271" cy="41" r="22" fill="#f4ecca" />
          <path d="m0 115 84-78 80 70 78-59 118 69v33H0" fill="#9fb8a7" />
          <path d="M0 99q78-59 168 1t192-5v55H0" fill="#6f9980" />
          <path d="M0 126q97-63 180-4t180-12v40H0" fill="#3d7d62" />
          <path
            d="M0 132q82-43 147-7m-134 20q60-31 113-13m103 11q61-32 131-26m-103 29q48-18 103-12"
            stroke="#add4a2"
            strokeWidth="3"
            fill="none"
          />
        </>
      ) : (
        <>
          <rect width="360" height="150" fill="#dee5fa" />
          <circle cx="276" cy="39" r="22" fill="#f6dcbc" />
          <path d="M0 118h360v32H0" fill="#a7bcdd" />
          <path
            d="M0 129q84-8 180 0t180 0m-360 12q90-8 180 0t180 0"
            stroke="#d9e4f3"
            fill="none"
          />
          <path
            d="M0 100h360M79 101V43m193 58V43M0 98q40-1 79-45 94 90 193 0 46 40 88 45"
            stroke="#737ca7"
            strokeWidth="4"
            fill="none"
          />
          <path
            d="M38 86v13m83-13v13m36-3v4m39-4v4m37-16v16m77-17v17"
            stroke="#8d98b9"
            strokeWidth="2"
          />
        </>
      )}
    </svg>
  );
}
