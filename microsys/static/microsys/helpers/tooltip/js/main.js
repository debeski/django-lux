(function () {
    'use strict';

    const tooltipConfigs = [
        {
            name: 'microsys',
            selector: '[data-ms-tooltip]',
            textAttribute: 'data-ms-tooltip',
            placementAttribute: 'data-ms-tooltip-placement',
            className: 'microsys-tooltip',
            defaultPlacement: 'top',
        },
        {
            name: 'sidebar',
            selector: '[data-ms-sidebar-tooltip]',
            textAttribute: 'data-ms-sidebar-tooltip',
            placementAttribute: 'data-ms-sidebar-tooltip-placement',
            className: 'sidebar-tooltip',
            defaultPlacement: 'right',
        },
    ];

    const tooltipGap = 10;
    const viewportGap = 8;
    let tooltip = null;
    let tooltipTarget = null;
    let tooltipConfig = null;
    let tooltipFrame = 0;

    document.addEventListener('DOMContentLoaded', initTooltips);

    function initTooltips() {
        if (window.__microsysTooltipInitialized) {
            return;
        }
        window.__microsysTooltipInitialized = true;

        tooltip = document.createElement('div');
        tooltip.className = 'ms-tooltip microsys-tooltip';
        tooltip.setAttribute('role', 'tooltip');
        document.body.appendChild(tooltip);

        document.addEventListener('pointerover', handlePointerOver);
        document.addEventListener('pointerout', handlePointerOut);
        document.addEventListener('focusin', handleFocusIn);
        document.addEventListener('focusout', handleFocusOut);
        document.addEventListener('click', hideTooltip);
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                hideTooltip();
            }
        });
        window.addEventListener('scroll', hideTooltip, true);
        window.addEventListener('resize', hideTooltip);
    }

    function matchTooltipTarget(source) {
        if (!(source instanceof Element)) {
            return null;
        }

        for (const config of tooltipConfigs) {
            const target = source.closest(config.selector);
            if (target && document.body.contains(target)) {
                return { target, config };
            }
        }
        return null;
    }

    function tooltipText(target, config) {
        return target && target.getAttribute(config.textAttribute);
    }

    function requestedPlacement(target, config) {
        const placement = target.getAttribute(config.placementAttribute);
        if (['top', 'right', 'bottom', 'left'].includes(placement)) {
            return placement;
        }
        return '';
    }

    function preferredPlacement(target, config) {
        const requested = requestedPlacement(target, config);
        if (requested) {
            return requested;
        }

        const rect = target.getBoundingClientRect();
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;

        if (config.defaultPlacement === 'right' && viewportWidth - rect.right >= 180) {
            return 'right';
        }
        if (rect.top < 96) {
            return 'bottom';
        }
        if (viewportWidth - rect.right < 180 && rect.left > 180) {
            return 'left';
        }
        if (rect.left < 180 && viewportWidth - rect.right > 180) {
            return 'right';
        }
        if (viewportHeight - rect.bottom < 120 && rect.top > 120) {
            return 'top';
        }
        return config.defaultPlacement || 'top';
    }

    function placementCandidates(preferred) {
        const fallback = {
            top: ['top', 'bottom', 'right', 'left'],
            bottom: ['bottom', 'top', 'right', 'left'],
            right: ['right', 'left', 'bottom', 'top'],
            left: ['left', 'right', 'bottom', 'top'],
        };
        return fallback[preferred] || fallback.top;
    }

    function coordinatesForPlacement(placement, targetRect, tooltipRect) {
        const centerX = targetRect.left + (targetRect.width / 2);
        const centerY = targetRect.top + (targetRect.height / 2);

        if (placement === 'bottom') {
            return {
                top: targetRect.bottom + tooltipGap,
                left: centerX - (tooltipRect.width / 2),
            };
        }
        if (placement === 'right') {
            return {
                top: centerY - (tooltipRect.height / 2),
                left: targetRect.right + tooltipGap,
            };
        }
        if (placement === 'left') {
            return {
                top: centerY - (tooltipRect.height / 2),
                left: targetRect.left - tooltipGap - tooltipRect.width,
            };
        }
        return {
            top: targetRect.top - tooltipGap - tooltipRect.height,
            left: centerX - (tooltipRect.width / 2),
        };
    }

    function overflowFor(coords, tooltipRect) {
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;

        return Math.max(
            viewportGap - coords.left,
            viewportGap - coords.top,
            (coords.left + tooltipRect.width + viewportGap) - viewportWidth,
            (coords.top + tooltipRect.height + viewportGap) - viewportHeight,
            0
        );
    }

    function clamp(value, min, max) {
        if (max < min) {
            return min;
        }
        return Math.min(Math.max(value, min), max);
    }

    function positionTooltip() {
        if (!tooltipTarget || !tooltipConfig || !tooltipText(tooltipTarget, tooltipConfig)) {
            return;
        }

        const targetRect = tooltipTarget.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        const candidates = placementCandidates(preferredPlacement(tooltipTarget, tooltipConfig));
        let best = {
            placement: candidates[0],
            coords: coordinatesForPlacement(candidates[0], targetRect, tooltipRect),
            overflow: Infinity,
        };

        candidates.forEach((placement) => {
            const coords = coordinatesForPlacement(placement, targetRect, tooltipRect);
            const overflow = overflowFor(coords, tooltipRect);
            if (overflow < best.overflow) {
                best = { placement, coords, overflow };
            }
        });

        const top = clamp(best.coords.top, viewportGap, viewportHeight - tooltipRect.height - viewportGap);
        const left = clamp(best.coords.left, viewportGap, viewportWidth - tooltipRect.width - viewportGap);
        const targetCenterX = targetRect.left + (targetRect.width / 2);
        const targetCenterY = targetRect.top + (targetRect.height / 2);
        const arrowX = clamp(targetCenterX - left, 12, tooltipRect.width - 12);
        const arrowY = clamp(targetCenterY - top, 12, tooltipRect.height - 12);

        tooltip.dataset.placement = best.placement;
        tooltip.dataset.tooltipKind = tooltipConfig.name;
        tooltip.style.left = `${Math.round(left)}px`;
        tooltip.style.top = `${Math.round(top)}px`;
        tooltip.style.setProperty('--ms-tooltip-arrow-x', `${Math.round(arrowX)}px`);
        tooltip.style.setProperty('--ms-tooltip-arrow-y', `${Math.round(arrowY)}px`);
        tooltip.classList.add('show');
    }

    function showTooltip(target, config) {
        const text = tooltipText(target, config);
        if (!text) {
            return;
        }

        window.cancelAnimationFrame(tooltipFrame);
        tooltipTarget = target;
        tooltipConfig = config;
        tooltip.className = `ms-tooltip ${config.className}`;
        tooltip.textContent = text;
        tooltip.classList.remove('show');
        tooltip.style.left = '0px';
        tooltip.style.top = '0px';
        tooltipFrame = window.requestAnimationFrame(positionTooltip);
    }

    function hideTooltip() {
        window.cancelAnimationFrame(tooltipFrame);
        tooltipTarget = null;
        tooltipConfig = null;
        if (tooltip) {
            tooltip.classList.remove('show');
        }
    }

    function handlePointerOver(event) {
        const match = matchTooltipTarget(event.target);
        if (match) {
            showTooltip(match.target, match.config);
        }
    }

    function handlePointerOut(event) {
        if (!tooltipTarget) {
            return;
        }
        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Node && tooltipTarget.contains(nextTarget)) {
            return;
        }
        hideTooltip();
    }

    function handleFocusIn(event) {
        const match = matchTooltipTarget(event.target);
        if (match) {
            showTooltip(match.target, match.config);
        }
    }

    function handleFocusOut(event) {
        if (tooltipTarget && event.target === tooltipTarget) {
            hideTooltip();
        }
    }
}());
