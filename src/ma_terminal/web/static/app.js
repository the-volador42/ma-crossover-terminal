// ---- Terminal state -------------------------------------------------
        let autoRefreshInterval = null;
        let ws = null;
        let streamingActive = false;
        let wsPort = Number(document.body.dataset.wsPort || 8765);
        let currentSignals = {};     // dedupe for the pop-up alerts
        let apiRetryCount = 0;
        let maxRetries = 3;
        let chartRenderInFlight = false;

        // uirevision keeps zoom/pan when Plotly re-renders after an update.
        function getUiRevision() {
            return getSelectedSymbol() + '::' + document.getElementById('timeframe').value + '::' + document.getElementById('mode').value;
        }

        updateChart();
        window.addEventListener('resize', () => Plotly.Plots.resize('chart'));

        // ---- Signal pop-up alerts -------------------------------------------
        function showNewSignalAlert(symbol, name, type, price, time) {
            const panel = document.getElementById('signalsPanel');
            const signalId = symbol + '-' + type + '-' + time;

            if (currentSignals[signalId]) return;
            currentSignals[signalId] = true;

            const triangle = type === 'BUY' ? '🔺' : '🔻';
            const typeLabel = type === 'BUY' ? 'ПОКУПКА' : 'ПРОДАЖА';

            const alert = document.createElement('div');
            alert.className = 'signal-alert ' + type;
            alert.innerHTML = `
                <div style="display: flex; align-items: center;">
                    <span class="triangle">${triangle}</span>
                    <div>
                        <strong>${name} (${symbol})</strong><br>
                        ${typeLabel}: ${price.toFixed(2)}<br>
                        <span class="signal-time">${time}</span>
                    </div>
                </div>
            `;

            alert.onclick = () => {
                document.getElementById('symbolSelect').value = symbol;
                handleSymbolChange();
                alert.remove();
            };

            panel.insertBefore(alert, panel.firstChild);

            // Auto-dismiss after 5 seconds.
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.style.opacity = '0';
                    alert.style.transition = 'opacity 0.5s';
                    setTimeout(() => alert.remove(), 500);
                }
            }, 5000);
        }

        // ---- Last-signals table ---------------------------------------------
        function updateLastSignals(signals) {
            const container = document.getElementById('lastSignalsList');

            if (!signals || signals.length === 0) {
                container.innerHTML = '<span style="color: #484f58;">Нет сигналов</span>';
                return;
            }

            let html = '<table style="width: 100%; border-collapse: collapse; font-size: 11px;">';
            html += '<tr style="border-bottom: 1px solid #30363d;">';
            html += '<th>Тикер</th><th>Тип</th><th>Цена</th><th>Время</th></tr>';

            signals.forEach(signal => {
                const badge = signal.type === 'BUY'
                    ? '<span class="signal-badge BUY">🔺 BUY</span>'
                    : '<span class="signal-badge SELL">🔻 SELL</span>';

                html += '<tr style="border-bottom: 1px solid #30363d;">';
                html += '<td><strong>' + signal.symbol + '</strong></td>';
                html += '<td>' + badge + '</td>';
                html += '<td>' + signal.price.toFixed(2) + '</td>';
                html += '<td style="font-size: 10px;">' + signal.time + '</td>';
                html += '</tr>';
            });

            html += '</table>';
            container.innerHTML = html;
        }

        // ---- Trading-mode stats ---------------------------------------------
        function updateTradingStats(stats) {
            const panel = document.getElementById('tradingStats');
            const mode = document.getElementById('mode').value;
            if (mode !== 'trading') {
                panel.style.display = 'none';
                return;
            }
            panel.style.display = 'flex';

            if (!stats) return;
            document.getElementById('statTrades').textContent = stats.total;
            document.getElementById('statWins').textContent = stats.wins;
            document.getElementById('statLosses').textContent = stats.losses;
            document.getElementById('statWinRate').textContent = stats.win_rate.toFixed(1) + '%';

            const pnlEl = document.getElementById('statTotalPnl');
            const pnlCard = document.getElementById('cardTotalPnl');
            const pnlVal = stats.total_pnl_pct;
            pnlEl.textContent = (pnlVal >= 0 ? '+' : '') + pnlVal.toFixed(2) + '%';
            pnlCard.classList.remove('pnl-pos', 'pnl-neg');
            pnlCard.classList.add(pnlVal >= 0 ? 'pnl-pos' : 'pnl-neg');

            const avgEl = document.getElementById('statAvgPnl');
            const avgCard = document.getElementById('cardAvgPnl');
            const avgVal = stats.avg_pnl_pct;
            avgEl.textContent = (avgVal >= 0 ? '+' : '') + avgVal.toFixed(2) + '%';
            avgCard.classList.remove('pnl-pos', 'pnl-neg');
            avgCard.classList.add(avgVal >= 0 ? 'pnl-pos' : 'pnl-neg');
        }

        // ---- Price display --------------------------------------------------
        function updateCurrentPrice(symbol, price) {
            if (getSelectedSymbol() === symbol) {
                document.getElementById('currentPriceDisplay').textContent =
                    '💰 Текущая цена: ' + price.toFixed(2) + ' ₽';
                document.getElementById('statPrice').textContent = price.toFixed(2);
            }
        }

        // ---- WebSocket plumbing ---------------------------------------------
        function connectWebSocket() {
            if (ws && ws.readyState === WebSocket.OPEN) return;

            try {
                ws = new WebSocket('ws://127.0.0.1:' + wsPort);

                ws.onopen = () => {
                    console.log('WebSocket подключен');
                    document.getElementById('streamIndicator').className = 'stream-indicator connected';
                    document.getElementById('statStream').textContent = 'ON';
                    apiRetryCount = 0;

                    // Ask the server to start streaming the current pair.
                    const symbol = getSelectedSymbol();
                    const timeframe = document.getElementById('timeframe').value;
                    ws.send(JSON.stringify({
                        type: 'subscribe',
                        symbol: symbol,
                        timeframe: timeframe
                    }));
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);

                    if (data.type === 'data_update') {
                        if (data.symbol === getSelectedSymbol()) {
                            updateChart(true);
                        }
                        document.getElementById('lastUpdate').textContent =
                            'Стрим: ' + new Date().toLocaleTimeString('ru-RU');
                    } else if (data.type === 'live_candle_update') {
                        if (data.symbol === getSelectedSymbol() &&
                            data.timeframe === document.getElementById('timeframe').value) {
                            updateLiveCandle(data.candle);
                        }
                    } else if (data.type === 'signals_update') {
                        updateLastSignals(data.signals);
                        if (data.signals && data.signals.length > 0) {
                            const lastSignal = data.signals[0];
                            showNewSignalAlert(
                                lastSignal.symbol,
                                lastSignal.name,
                                lastSignal.type,
                                lastSignal.price,
                                lastSignal.time
                            );
                        }
                    } else if (data.type === 'prices_update') {
                        if (data.prices) {
                            Object.entries(data.prices).forEach(([ticker, price]) => {
                                updateCurrentPrice(ticker, price);
                            });
                        }
                    }
                };

                ws.onclose = () => {
                    console.log('WebSocket отключен');
                    document.getElementById('streamIndicator').className = 'stream-indicator disconnected';
                    document.getElementById('statStream').textContent = 'OFF';
                    if (streamingActive) {
                        setTimeout(connectWebSocket, 5000);
                    }
                };

                ws.onerror = (error) => {
                    console.error('WebSocket ошибка:', error);
                };

            } catch (error) {
                console.error('Ошибка подключения WebSocket:', error);
            }
        }

        function toggleStreaming() {
            const btn = document.getElementById('streamBtn');
            streamingActive = !streamingActive;

            if (streamingActive) {
                btn.classList.add('active');
                btn.textContent = '📡 СТРИМ ON';
                connectWebSocket();
                updateStatus('stream', '📡 Стриминг активирован');
            } else {
                btn.classList.remove('active');
                btn.textContent = '📡 СТРИМ';
                if (ws) ws.close();
                document.getElementById('streamIndicator').className = 'stream-indicator disconnected';
                document.getElementById('statStream').textContent = 'OFF';
                updateStatus('stopped', 'Стриминг остановлен');
            }
        }

        // ---- UI event handlers ----------------------------------------------
        function handleSymbolChange() {
            const sel = document.getElementById('symbolSelect').value;
            document.getElementById('customSymbolGroup').style.display = sel === '__custom__' ? 'flex' : 'none';
            if (sel !== '__custom__') {
                updateChart();
                if (streamingActive && ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: 'subscribe',
                        symbol: sel,
                        timeframe: document.getElementById('timeframe').value
                    }));
                }
            }
        }

        function handleTimeframeChange() {
            updateChart();
            const symbol = getSelectedSymbol();
            if (streamingActive && ws && ws.readyState === WebSocket.OPEN && symbol) {
                ws.send(JSON.stringify({
                    type: 'subscribe',
                    symbol: symbol,
                    timeframe: document.getElementById('timeframe').value
                }));
            }
        }

        function handleModeChange() {
            updateChart();
        }

        function getSelectedSymbol() {
            const sel = document.getElementById('symbolSelect').value;
            return sel === '__custom__' ? document.getElementById('customSymbol').value.trim().toUpperCase() : sel;
        }

        function resetZoom() {
            const chartDiv = document.getElementById('chart');
            Plotly.relayout(chartDiv, {
                'xaxis.autorange': true,
                'yaxis.autorange': true
            });
            updateStatus('success', '🔍 Масштаб сброшен');
        }

        // ---- Chart rendering -------------------------------------------------
        function renderChart(chartData) {
            const traces = [{
                x: chartData.candles.x, open: chartData.candles.open, high: chartData.candles.high,
                low: chartData.candles.low, close: chartData.candles.close,
                type: 'candlestick', name: 'Цена',
                increasing: { line: { color: '#26a69a' } },
                decreasing: { line: { color: '#ef5350' } },
                opacity: 0.9
            }];

            // Slow EMA goes first so the fast EMA draws on top of it.
            if (chartData.ema_slow) {
                traces.push({
                    x: chartData.candles.x,
                    y: chartData.ema_slow.y,
                    mode: 'lines',
                    name: 'EMA ' + chartData.ema_slow.period + ' (slow)',
                    type: 'scatter',
                    line: { color: chartData.ema_slow.color, width: chartData.ema_slow.width },
                    hoverinfo: 'y+name'
                });
            }
            if (chartData.ema_fast) {
                traces.push({
                    x: chartData.candles.x,
                    y: chartData.ema_fast.y,
                    mode: 'lines',
                    name: 'EMA ' + chartData.ema_fast.period + ' (fast)',
                    type: 'scatter',
                    line: { color: chartData.ema_fast.color, width: chartData.ema_fast.width },
                    hoverinfo: 'y+name'
                });
            }

            const buys = (chartData.signals || []).filter(s => s.type === 'BUY');
            const sells = (chartData.signals || []).filter(s => s.type === 'SELL');

            if (buys.length) traces.push({
                x: buys.map(s => s.time),
                y: buys.map(s => s.price),
                mode: 'markers',
                name: '▲ Покупка (вход)',
                type: 'scatter',
                marker: {
                    symbol: 'triangle-up', size: 15, color: '#26a69a',
                    line: { color: 'white', width: 1 }
                },
                hovertemplate: '<b>▲ ПОКУПКА</b><br>%{x}<br>Цена: %{y:.2f}<extra></extra>'
            });

            if (sells.length) traces.push({
                x: sells.map(s => s.time),
                y: sells.map(s => s.price),
                mode: 'markers',
                name: '▼ Продажа (выход)',
                type: 'scatter',
                // customdata carries the exit reason so the tooltip can show it
                customdata: sells.map(s => s.reason || ''),
                marker: {
                    symbol: 'triangle-down', size: 15, color: '#ef5350',
                    line: { color: 'white', width: 1 }
                },
                hovertemplate: '<b>▼ ПРОДАЖА</b> (%{customdata})<br>%{x}<br>Цена: %{y:.2f}<extra></extra>'
            });

            const layout = {
                template: 'plotly_dark', hovermode: 'x unified',
                uirevision: getUiRevision(),
                xaxis: { title: 'Время (МСК)', type: 'category', rangeslider: { visible: false }, gridcolor: '#30363d' },
                yaxis: { title: 'Цена', gridcolor: '#30363d' },
                margin: { l: 60, r: 40, t: 10, b: 50 },
                paper_bgcolor: '#0d1117', plot_bgcolor: '#0d1117',
                font: { color: '#c9d1d9' }, dragmode: 'pan',
                legend: {
                    x: 0.01, y: 0.99,
                    bgcolor: 'rgba(22, 27, 34, 0.85)',
                    bordercolor: '#30363d',
                    font: { size: 10 }
                }
            };

            const config = { scrollZoom: true, displayModeBar: true, displaylogo: false, responsive: true };

            const chartDiv = document.getElementById('chart');

            chartRenderInFlight = true;
            Plotly.react(chartDiv, traces, layout, config)
                .then(() => {
                    updateLivePriceLine(chartDiv, chartData.last_price);
                })
                .catch((err) => {
                    console.error('Ошибка рендера графика:', err);
                    showError('❌ Ошибка отрисовки графика');
                })
                .finally(() => {
                    chartRenderInFlight = false;
                });
        }

        // ---- Fast-path live candle update (no full re-render) ----------------
        function updateLiveCandle(candle) {
            const chartDiv = document.getElementById('chart');
            if (!chartDiv || !chartDiv.data || !chartDiv.data.length || !candle || !candle.time) return;
            if (chartRenderInFlight) return;

            try {
                const trace = chartDiv.data[0];
                if (!trace || trace.type !== 'candlestick' || !trace.x) return;

                const xs = trace.x;
                const lastIdx = xs.length - 1;

                const newX = xs.slice();
                const newOpen = trace.open.slice();
                const newHigh = trace.high.slice();
                const newLow = trace.low.slice();
                const newClose = trace.close.slice();

                if (lastIdx >= 0 && xs[lastIdx] === candle.time) {
                    newOpen[lastIdx] = candle.open;
                    newHigh[lastIdx] = candle.high;
                    newLow[lastIdx] = candle.low;
                    newClose[lastIdx] = candle.close;
                } else {
                    newX.push(candle.time);
                    newOpen.push(candle.open);
                    newHigh.push(candle.high);
                    newLow.push(candle.low);
                    newClose.push(candle.close);
                }

                Plotly.restyle(chartDiv, {
                    x: [newX], open: [newOpen], high: [newHigh], low: [newLow], close: [newClose]
                }, [0]);

                updateLivePriceLine(chartDiv, candle.close);

                document.getElementById('statPrice').textContent = candle.close.toFixed(2);
                document.getElementById('statCache').textContent = 'live';
                updateCurrentPrice(getSelectedSymbol(), candle.close);
                document.getElementById('lastUpdate').textContent =
                    '🔴 Live: ' + new Date().toLocaleTimeString('ru-RU');
            } catch (err) {
                console.error('Ошибка live-обновления свечи:', err);
            }
        }

        // ---- Dotted horizontal line for the current price -------------------
        function updateLivePriceLine(chartDiv, price) {
            if (!price) return;
            Plotly.relayout(chartDiv, {
                shapes: [{
                    type: 'line', xref: 'paper', x0: 0, x1: 1,
                    yref: 'y', y0: price, y1: price,
                    line: { color: '#58a6ff', width: 1, dash: 'dot' }
                }],
                annotations: [{
                    xref: 'paper', x: 1, xanchor: 'left',
                    yref: 'y', y: price,
                    text: '  ' + price.toFixed(2),
                    showarrow: false, align: 'left',
                    bgcolor: '#1f6feb', bordercolor: '#58a6ff',
                    font: { color: '#fff', size: 11 }
                }]
            });
        }

        // ---- Main data fetcher ----------------------------------------------
        async function updateChart(silent = false) {
            const symbol = getSelectedSymbol();
            if (!symbol) { showError('❌ Укажите тикер'); return; }

            if (!silent) showLoading(true);
            updateStatus('loading', 'Загрузка...');

            try {
                const params = new URLSearchParams({
                    symbol,
                    timeframe: document.getElementById('timeframe').value,
                    mode: document.getElementById('mode').value
                });

                const response = await fetch('/api/update?' + params);

                // Basic retry-on-throttle behaviour: T-Invest sometimes answers
                // 429/503 when the rate limit is hit.
                if (response.status === 429 || response.status === 503) {
                    if (apiRetryCount < maxRetries) {
                        apiRetryCount++;
                        const delay = apiRetryCount * 2000;
                        updateStatus('loading', 'Ожидание API (' + delay/1000 + ' сек)...');
                        await new Promise(resolve => setTimeout(resolve, delay));
                        return updateChart(silent);
                    } else {
                        throw new Error('Превышено количество попыток.');
                    }
                }

                const data = await response.json();
                if (data.error) throw new Error(data.error);

                apiRetryCount = 0;
                renderChart(data.chart_data);
                document.getElementById('statSignals').textContent = data.signals_count;
                document.getElementById('statBuys').textContent = data.buys_count;
                document.getElementById('statSells').textContent = data.sells_count;
                document.getElementById('statCandles').textContent = data.candles_count;
                document.getElementById('statPrice').textContent = data.last_price.toFixed(2);

                const ageMin = Math.floor(data.cache_age_seconds / 60);
                document.getElementById('statCache').textContent = data.cache_age_seconds < 30 ? 'live' : (ageMin + ' мин');
                document.getElementById('lastUpdate').textContent = 'Обновлено: ' + new Date().toLocaleTimeString('ru-RU');

                updateTradingStats(data.trades_stats);
                updateLastSignals(data.last_signals);

                if (data.current_prices) {
                    Object.entries(data.current_prices).forEach(([ticker, price]) => {
                        updateCurrentPrice(ticker, price);
                    });
                }

                const modeLabel = data.mode === 'trading' ? ' [Торговля]' : '';
                updateStatus('success', '✅ Данные загружены' + (data.from_cache ? ' (кэш)' : ' (API)') + modeLabel);
            } catch (error) {
                showError('❌ ' + error.message);
                updateStatus('error', 'Ошибка загрузки');
            } finally {
                if (!silent) showLoading(false);
            }
        }

        // ---- Auto-refresh toggle --------------------------------------------
        function toggleAutoRefresh() {
            const btn = document.getElementById('autoBtn');
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
                btn.classList.remove('active');
                btn.textContent = '▶ АВТО';
                updateStatus('stopped', 'Автообновление остановлено');
            } else {
                const intervals = { "1m": 60, "10m": 600, "1h": 3600, "1d": 86400, "1w": 604800, "1M": 2592000 };
                const seconds = intervals[document.getElementById('timeframe').value] || 600;
                updateChart();
                autoRefreshInterval = setInterval(() => {
                    // When the stream is active, polling would double the load —
                    // the stream already pushes fresh data.
                    if (streamingActive && ws && ws.readyState === WebSocket.OPEN) return;
                    updateChart();
                }, seconds * 1000);
                btn.classList.add('active');
                btn.textContent = '⏸ СТОП';
                updateStatus('active', '● Авто: каждые ' + (seconds >= 60 ? Math.floor(seconds/60) + ' мин' : seconds + ' сек'));
            }
        }

        // ---- Small helpers --------------------------------------------------
        function showLoading(show) { document.getElementById('loading').classList.toggle('active', show); }

        function updateStatus(type, message) {
            const dots = {
                'loading': '<span style="color:#d29922;">●</span>',
                'success': '<span style="color:#3fb950;">●</span>',
                'active': '<span style="color:#3fb950;">●</span>',
                'error': '<span style="color:#da3633;">●</span>',
                'stopped': '<span style="color:#da3633;">●</span>',
                'stream': '<span style="color:#6f42c1;">●</span>'
            };
            document.getElementById('statusText').innerHTML = (dots[type] || '') + ' ' + message;
        }

        function showError(message) {
            const toast = document.getElementById('errorToast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 4000);
        }

        document.addEventListener('keypress', (e) => { if (e.key === 'Enter' && !autoRefreshInterval) updateChart(); });
