import numpy as np


def plot_full_charts(gui, trend_data, logging):
    """Compact but comprehensive chart plotting for trading dashboard with defensive checks."""
    try:
        # Safety check for input
        if not trend_data:
            raise ValueError("trend_data is None or empty")

        gui.fig.clear()
        gui.fig.patch.set_facecolor('#1e2328')

        # Create subplots with tight spacing
        gs = gui.fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.35)
        ax_price = gui.fig.add_subplot(gs[0])
        ax_macd = gui.fig.add_subplot(gs[1], sharex=ax_price)
        ax_rsi = gui.fig.add_subplot(gs[2], sharex=ax_price)

        # Configure axes appearance
        for ax in [ax_price, ax_macd, ax_rsi]:
            ax.set_facecolor('#1e2328')
            ax.tick_params(axis='both', colors='#b0bec5', labelsize=6)
            for spine in ax.spines.values():
                spine.set_color('#37474f')
            ax.grid(True, color='#37474f', alpha=0.15, linestyle='--')

        def clean_list(data):
            """Safely convert data to list of floats, handling None and non-numeric values."""
            if data is None:
                return []
            try:
                return [float(x) if x is not None and str(x).lower() != 'nan' else np.nan for x in data]
            except (TypeError, ValueError):
                logging.warning(f"Could not convert data to float list: {type(data)}")
                return []
            except Exception as e:
                logging.error(f"Unexpected error in clean_list: {e}")
                return []

        # Defensive extraction of all series
        close_prices = clean_list(trend_data.get('close') or [])
        if not close_prices:
            raise ValueError("No valid close prices available")

        x_axis = range(len(close_prices))

        # Price Chart
        ax_price.plot(x_axis, close_prices, color='#00d4ff', linewidth=1.2, alpha=0.9, label='Price')

        # SuperTrend
        st_data = trend_data.get('super_trend_short') or {}
        st_values = clean_list(st_data.get('trend'))
        if len(st_values) == len(close_prices):
            ax_price.plot(x_axis, st_values, color='#ffa726', linestyle='--',
                          linewidth=0.8, alpha=0.8, label='SuperTrend')
        elif st_values:
            logging.warning("SuperTrend length mismatch with close prices")

        # Bollinger Bands
        bb_data = trend_data.get('bb') or {}
        bb_upper = clean_list(bb_data.get('upper'))
        bb_mid = clean_list(bb_data.get('middle'))
        bb_lower = clean_list(bb_data.get('lower'))

        if all(len(x) == len(close_prices) for x in [bb_upper, bb_mid, bb_lower]):
            ax_price.plot(x_axis, bb_upper, color='#00ff88', linestyle=':',
                          linewidth=0.7, alpha=0.7, label='BB Upper')
            ax_price.plot(x_axis, bb_mid, color='#b0bec5', linestyle='-',
                          linewidth=0.6, alpha=0.6, label='BB Mid')
            ax_price.plot(x_axis, bb_lower, color='#ff4757', linestyle=':',
                          linewidth=0.7, alpha=0.7, label='BB Lower')
        elif any([bb_upper, bb_mid, bb_lower]):
            logging.warning("Bollinger Bands length mismatch with close prices")

        ax_price.set_ylabel('Price', color='#b0bec5', fontsize=7)
        ax_price.legend(loc='upper left', fontsize=6, facecolor='#2a2f36', framealpha=0.8)
        ax_price.set_title('Price & Indicators', color='#ffffff', fontsize=8, pad=6)

        # MACD
        macd_data = trend_data.get('macd') or {}
        macd_line = clean_list(macd_data.get('macd'))
        signal_line = clean_list(macd_data.get('signal'))
        histogram = clean_list(macd_data.get('histogram'))

        if all(len(x) == len(close_prices) for x in [macd_line, signal_line, histogram]):
            ax_macd.plot(x_axis, macd_line, color='#00d4ff', linewidth=0.8, label='MACD')
            ax_macd.plot(x_axis, signal_line, color='#ff4757', linewidth=0.8, label='Signal')

            # Safely determine histogram colors
            colors = ['#00ff88' if (not np.isnan(val) and val >= 0) else '#ff4757'
                      for val in histogram]
            ax_macd.bar(x_axis, histogram, color=colors, width=0.6, alpha=0.6,
                        label='Histogram')

            ax_macd.axhline(0, color='#37474f', linestyle='-', linewidth=0.5)
            ax_macd.legend(loc='upper left', fontsize=6, facecolor='#2a2f36', framealpha=0.8)
        elif any([macd_line, signal_line, histogram]):
            logging.warning("MACD data length mismatch with close prices")

        ax_macd.set_title('MACD', color='#ffffff', fontsize=7, pad=5)
        ax_macd.set_ylabel('MACD', color='#b0bec5', fontsize=7)

        # RSI
        rsi_values = clean_list(trend_data.get('rsi_series'))
        if len(rsi_values) == len(close_prices):
            ax_rsi.plot(x_axis, rsi_values, color='#b39ddb', linewidth=1.0, label='RSI')
            ax_rsi.axhline(60, color='#ff4757', linestyle='--', linewidth=0.7, alpha=0.7)
            ax_rsi.axhline(40, color='#00ff88', linestyle='--', linewidth=0.7, alpha=0.7)
            ax_rsi.axhline(50, color='#37474f', linestyle='-', linewidth=0.5, alpha=0.5)
            ax_rsi.fill_between(x_axis, 60, 100, color='#ff4757', alpha=0.1)
            ax_rsi.fill_between(x_axis, 0, 40, color='#00ff88', alpha=0.1)
            ax_rsi.legend(loc='upper left', fontsize=6, facecolor='#2a2f36', framealpha=0.8)
        elif rsi_values:
            logging.warning("RSI length mismatch with close prices")

        ax_rsi.set_title('RSI', color='#ffffff', fontsize=7, pad=5)
        ax_rsi.set_ylabel('RSI', color='#b0bec5', fontsize=7)
        ax_rsi.set_xlabel('Time', color='#b0bec5', fontsize=7)
        ax_rsi.set_ylim(0, 100)

        # Final touches
        gui.fig.suptitle('Market Dashboard', color='#ffffff', fontsize=9, y=0.97)
        gui.canvas.draw()

    except Exception as e:
        logging.error(f"Chart plotting error: {e}", exc_info=True)
        # Fallback empty chart
        gui.fig.clear()
        ax = gui.fig.add_subplot(111)
        ax.set_facecolor('#1e2328')
        ax.text(0.5, 0.5, 'Chart data unavailable\nPlease wait for updates...',
                ha='center', va='center', color='#ffffff', fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
        gui.canvas.draw()