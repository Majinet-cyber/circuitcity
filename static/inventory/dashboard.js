const options = {
  maintainAspectRatio: false,
  scales: {
    x: {
      type: 'category',
      ticks: {
        autoSkip: false,
        maxRotation: 0,
        callback: (v) => data.labels[v]   // ensures the label text shows
      }
    },
    y: {
      beginAtZero: true,
      grace: '5%'
    }
  },
  plugins: {
    legend: { display: false }
  }
};
