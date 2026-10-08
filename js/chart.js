/**
 * WFI MINING - COMPONENT BIỂU ĐỒ ĐƯỜNG TƯƠNG TÁC (CHART COMPONENT)
 * Tự vẽ SVG với đường cong mượt, dải gradient xanh lá, tương tác tooltip mượt mà
 */

class MiningChart {
  constructor(containerId, svgId) {
    this.container = document.getElementById(containerId);
    this.svg = document.getElementById(svgId);
    this.linePath = document.getElementById('chartLinePath');
    this.areaPath = document.getElementById('chartAreaPath');
    this.pointsGroup = document.getElementById('chartPointsGroup');
    this.gridLinesGroup = document.getElementById('gridLines');
    this.xLabelsContainer = document.getElementById('chartXLabels');
    this.tooltip = document.getElementById('chartTooltip');
    this.tooltipDate = document.getElementById('tooltipDate');
    this.tooltipValue = document.getElementById('tooltipValue');
    this.cursorLine = document.getElementById('cursorLine');

    this.currentPeriod = "7";
    this.activePointIndex = null;

    this.init();
  }

  init() {
    this.bindEvents();
    this.renderPeriod(this.currentPeriod);
  }

  bindEvents() {
    // Chuyển tab thời gian 7 ngày / 30 ngày / 90 ngày
    const tabs = document.querySelectorAll('.filter-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', (e) => {
        tabs.forEach(t => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');

        const period = tab.getAttribute('data-period');
        this.renderPeriod(period);
      });
    });

    // Resize listener để đảm bảo tọa độ tooltip khớp khi resize cửa sổ
    window.addEventListener('resize', () => {
      this.hideTooltip();
    });
  }

  renderPeriod(period) {
    this.currentPeriod = period;
    const periodData = WfiDataService.chartData[period];
    if (!periodData) return;

    // Cập nhật thông số tóm tắt chu kỳ
    const totalEl = document.getElementById('chartPeriodTotal');
    const avgEl = document.getElementById('chartPeriodAverage');
    const peakEl = document.getElementById('chartPeriodPeak');

    if (totalEl) totalEl.textContent = `${WfiDataService.formatNumberVN(periodData.total)} WFI`;
    if (avgEl) avgEl.textContent = `${WfiDataService.formatNumberVN(periodData.average)} WFI`;
    if (peakEl) peakEl.textContent = `${WfiDataService.formatNumberVN(periodData.peak)} WFI`;

    // Chuẩn bị vẽ SVG
    const width = 760;
    const height = 240;
    const paddingX = 40;
    const paddingTop = 25;
    const paddingBottom = 30;

    const values = periodData.values;
    const minVal = Math.min(...values) * 0.85;
    const maxVal = Math.max(...values) * 1.1;

    // Tính toán tọa độ điểm
    const points = values.map((val, idx) => {
      const x = paddingX + (idx / (values.length - 1)) * (width - paddingX * 2);
      const normalizedY = (val - minVal) / (maxVal - minVal);
      const y = height - paddingBottom - normalizedY * (height - paddingTop - paddingBottom);
      return { x, y, val, label: periodData.labels[idx], fullDate: periodData.fullDates[idx] };
    });

    // Vẽ lưới ngang
    this.renderGrid(width, height, paddingTop, paddingBottom);

    // Tạo đường cong mượt (Smooth Bezier Curve)
    const linePathD = this.generateSmoothPath(points);
    this.linePath.setAttribute('d', linePathD);

    // Tạo vùng đổ màu gradient khép kín
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];
    const areaPathD = `${linePathD} L ${lastPoint.x} ${height - paddingBottom} L ${firstPoint.x} ${height - paddingBottom} Z`;
    this.areaPath.setAttribute('d', areaPathD);

    // Render các điểm tròn và gắn sự kiện tooltip
    this.renderPoints(points);

    // Render nhãn thời gian trục hoành
    this.renderXLabels(periodData.labels);
  }

  generateSmoothPath(points) {
    if (points.length === 0) return '';
    if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

    let path = `M ${points[0].x} ${points[0].y}`;

    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i === 0 ? 0 : i - 1];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;

      // Tính điểm điều khiển Catmull-Rom chuyển sang Bezier
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;

      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      path += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
    }

    return path;
  }

  renderGrid(width, height, paddingTop, paddingBottom) {
    this.gridLinesGroup.innerHTML = '';
    const steps = 4;
    const availableHeight = height - paddingTop - paddingBottom;

    for (let i = 0; i <= steps; i++) {
      const y = paddingTop + (i / steps) * availableHeight;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '20');
      line.setAttribute('y1', y);
      line.setAttribute('x2', (width - 20).toString());
      line.setAttribute('y2', y);
      line.setAttribute('class', 'chart-grid-line');
      this.gridLinesGroup.appendChild(line);
    }
  }

  renderPoints(points) {
    this.pointsGroup.innerHTML = '';
    points.forEach((pt, index) => {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', pt.x);
      circle.setAttribute('cy', pt.y);
      circle.setAttribute('r', '4');
      circle.setAttribute('class', 'chart-point');
      circle.setAttribute('data-index', index);

      // Tương tác hover / click
      const show = () => this.showTooltip(pt);
      const hide = () => this.hideTooltip();

      circle.addEventListener('mouseenter', show);
      circle.addEventListener('mouseleave', hide);
      circle.addEventListener('click', show);
      circle.addEventListener('touchstart', (e) => {
        e.preventDefault();
        show();
      });

      this.pointsGroup.appendChild(circle);
    });
  }

  renderXLabels(labels) {
    this.xLabelsContainer.innerHTML = '';
    labels.forEach(lbl => {
      const span = document.createElement('span');
      span.textContent = lbl;
      this.xLabelsContainer.appendChild(span);
    });
  }

  showTooltip(point) {
    this.tooltipDate.textContent = `Thời gian: ${point.fullDate}`;
    this.tooltipValue.textContent = `+${WfiDataService.formatNumberVN(point.val)} WFI`;

    // Tính toán tọa độ hiển thị trong container
    const svgRect = this.svg.getBoundingClientRect();
    const containerRect = this.container.getBoundingClientRect();

    const scaleX = svgRect.width / 760;
    const scaleY = svgRect.height / 280;

    const screenX = point.x * scaleX;
    const screenY = point.y * scaleY;

    this.tooltip.style.left = `${screenX}px`;
    this.tooltip.style.top = `${screenY}px`;
    this.tooltip.classList.add('visible');

    // Đường gióng đứng
    if (this.cursorLine) {
      this.cursorLine.setAttribute('x1', point.x);
      this.cursorLine.setAttribute('x2', point.x);
      this.cursorLine.style.opacity = '0.7';
    }
  }

  hideTooltip() {
    if (this.tooltip) {
      this.tooltip.classList.remove('visible');
    }
    if (this.cursorLine) {
      this.cursorLine.style.opacity = '0';
    }
  }
}
