(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: Commission Comparison ---
  var chartEl = document.getElementById('chart-commission');
  if (chartEl) {
    var chart = echarts.init(chartEl, null, { renderer: 'svg' });
    chart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        axisPointer: { type: 'shadow' },
        formatter: function(params) {
          var html = '<div style="font-weight:700;margin-bottom:6px">' + params[0].name + '</div>';
          params.forEach(function(p) {
            html += '<div style="color:' + p.color + '">' + p.seriesName + ': ¥' + p.value + '</div>';
          });
          return html;
        }
      },
      legend: {
        data: ['开发者收入', 'Apple 佣金'],
        bottom: 0,
        textStyle: { color: muted, fontSize: 13 },
        itemWidth: 14,
        itemHeight: 14,
        itemGap: 30
      },
      grid: {
        left: '8%',
        right: '8%',
        top: 30,
        bottom: 50
      },
      xAxis: {
        type: 'category',
        data: ['标准费率 (30%)', '小型企业计划 (15%)'],
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: ink, fontSize: 13, fontWeight: 600 },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        name: '金额 (¥)',
        nameTextStyle: { color: muted, fontSize: 12 },
        axisLine: { show: false },
        axisLabel: { color: muted, fontSize: 12 },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [
        {
          name: '开发者收入',
          type: 'bar',
          data: [70, 85],
          itemStyle: {
            color: accent,
            borderRadius: [6, 6, 0, 0]
          },
          barWidth: '30%',
          label: {
            show: true,
            position: 'top',
            color: ink,
            fontSize: 14,
            fontWeight: 700,
            formatter: '¥{c}'
          }
        },
        {
          name: 'Apple 佣金',
          type: 'bar',
          data: [30, 15],
          itemStyle: {
            color: accent2,
            borderRadius: [6, 6, 0, 0]
          },
          barWidth: '30%',
          label: {
            show: true,
            position: 'top',
            color: ink,
            fontSize: 14,
            fontWeight: 700,
            formatter: '¥{c}'
          }
        }
      ]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  }
})();
