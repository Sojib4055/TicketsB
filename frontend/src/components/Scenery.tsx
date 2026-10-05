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
          <stop offset="1" stopColor="#cdcbd6" />
        </linearGradient>
      </defs>
      <circle cx="428" cy="86" r="63" fill="white" opacity=".055" />
      <circle cx="428" cy="86" r="92" stroke="white" strokeOpacity=".09" />
      <circle cx="428" cy="86" r="121" stroke="white" strokeOpacity=".06" />
      <path
        d="M-20 241C138 113 291 342 617 86"
        stroke="#596235"
        strokeWidth="66"
        opacity=".14"
      />
      <path
        d="M-20 241C138 113 291 342 617 86"
        stroke="#fff1de"
        strokeDasharray="11 13"
        opacity=".55"
      />
      <path
        d="M411 58V40m-8 9h16M164 124v-12m-6 6h12"
        stroke="#fff1de"
        strokeWidth="2"
      />
      <circle cx="503" cy="169" r="4" fill="#e4edc9" />
      <g transform="translate(112 43) rotate(-8 190 110)">
        <ellipse
          cx="220"
          cy="181"
          rx="139"
          ry="19"
          fill="#2f3020"
          opacity=".22"
        />
        <path
          d="M87 87q0-22 22-22h183q23 0 29 25l14 71H87Z"
          fill="url(#bus-body)"
        />
        <path d="M96 92q0-16 14-16h176q13 0 18 17l8 30H96Z" fill="#2f3020" />
        <path
          d="M111 81h26v37h-26zm34 0h28v37h-28zm36 0h28v37h-28zm36 0h28v37h-28zm37 0h28q10 0 14 14l6 23h-48z"
          fill="#8f9878"
        />
        <path d="M91 132h231l5 18H91" fill="#596235" />
        <path d="M234 132h88l5 18h-88" fill="#41492d" />
        <rect x="84" y="150" width="251" height="14" rx="5" fill="#fff8ed" />
        <circle cx="127" cy="162" r="20" fill="#2f3020" />
        <circle cx="127" cy="162" r="10" fill="#aaa8b3" />
        <circle cx="290" cy="162" r="20" fill="#2f3020" />
        <circle cx="290" cy="162" r="10" fill="#aaa8b3" />
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
        <circle cx="22" cy="22" r="10" fill="#edf0df" />
        <path
          d="m18 22 3 3 5-6"
          stroke="#596235"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <text
          x="40"
          y="19"
          fill="#2f3020"
          fontSize="9"
          fontFamily="Arial"
          fontWeight="bold"
        >
          Less refreshing.
        </text>
        <text x="40" y="31" fill="#6c6b61" fontSize="8" fontFamily="Arial">
          More going places.
        </text>
      </g>
      <g transform="translate(149 196)">
        <rect width="91" height="34" rx="10" fill="#cdcbd6" />
        <path d="M14 10v14m-4-4 4 4 4-4" stroke="#3b3744" strokeWidth="1.5" />
        <text
          x="28"
          y="21"
          fill="#3b3744"
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
          <rect width="360" height="150" fill="#f5ddcb" />
          <circle cx="272" cy="52" r="28" fill="#d96846" />
          <path d="M0 89q70-13 160 5t200-8v64H0" fill="#b6b3c3" />
          <path d="M0 110q83-18 174 6t186-7v41H0" fill="#8c899f" />
          <path d="M0 134q116-26 360 5v11H0" fill="#ead9ba" />
          <path
            d="M45 128q9-47-7-68m3 4q-36-17-38 11m38-11q27-28 51-4m-52 5q-4-28-33-29m35 27q22-4 31 19"
            stroke="#596235"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
          <path d="m173 41 6-4 6 4m8 7 5-3 5 3" stroke="#936650" fill="none" />
        </>
      ) : type === "hills" ? (
        <>
          <rect width="360" height="150" fill="#e6e8d6" />
          <circle cx="271" cy="41" r="22" fill="#f0c69e" />
          <path d="m0 115 84-78 80 70 78-59 118 69v33H0" fill="#b2b993" />
          <path d="M0 99q78-59 168 1t192-5v55H0" fill="#818b58" />
          <path d="M0 126q97-63 180-4t180-12v40H0" fill="#596235" />
          <path
            d="M0 132q82-43 147-7m-134 20q60-31 113-13m103 11q61-32 131-26m-103 29q48-18 103-12"
            stroke="#b9c28c"
            strokeWidth="3"
            fill="none"
          />
        </>
      ) : (
        <>
          <rect width="360" height="150" fill="#e3e0e9" />
          <circle cx="276" cy="39" r="22" fill="#d96846" />
          <path d="M0 118h360v32H0" fill="#b6b2c5" />
          <path
            d="M0 129q84-8 180 0t180 0m-360 12q90-8 180 0t180 0"
            stroke="#e3dfeb"
            fill="none"
          />
          <path
            d="M0 100h360M79 101V43m193 58V43M0 98q40-1 79-45 94 90 193 0 46 40 88 45"
            stroke="#686178"
            strokeWidth="4"
            fill="none"
          />
          <path
            d="M38 86v13m83-13v13m36-3v4m39-4v4m37-16v16m77-17v17"
            stroke="#817a91"
            strokeWidth="2"
          />
        </>
      )}
    </svg>
  );
}
