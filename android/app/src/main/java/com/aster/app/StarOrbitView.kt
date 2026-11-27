package com.aster.app

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View
import android.view.animation.LinearInterpolator
import androidx.core.content.ContextCompat
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * 连接页顶部的动态星标，复刻桌面 HeroLogo：
 * 两条旋转椭圆轨道 + 轨道小点 + 呼吸光晕 + 渐变八角星 + 中心白点。
 *
 * 只依赖平台 Canvas 与 ValueAnimator，不新增第三方库；View detach 时停止动画。
 */
class StarOrbitView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    private val density = resources.displayMetrics.density
    private val blue = ContextCompat.getColor(context, R.color.aster_blue)
    private val blueLight = ContextCompat.getColor(context, R.color.aster_blue_light)
    private val mint = ContextCompat.getColor(context, R.color.aster_mint)
    private val mintLight = ContextCompat.getColor(context, R.color.aster_mint_light)
    private val white = ContextCompat.getColor(context, R.color.aster_white)

    private val orbitPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 0.9f * density
    }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val starHaloPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val starPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val coreGlowPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val corePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val starPath = Path()

    private var centerX = 0f
    private var centerY = 0f
    private var glowRadius = 0f
    private var starRadius = 0f
    private var orbitRadiusA = 0f
    private var orbitRadiusB = 0f

    private var phase = 0f
    private var animator: ValueAnimator? = null

    init {
        setWillNotDraw(false)
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        super.onSizeChanged(width, height, oldWidth, oldHeight)
        centerX = width / 2f
        centerY = height / 2f
        val radius = minOf(width, height) / 2f * 0.94f
        glowRadius = radius * 1.08f
        starRadius = radius * 0.52f
        orbitRadiusA = radius * 0.86f
        orbitRadiusB = radius * 0.66f
        buildStarPath()
        glowPaint.shader = RadialGradient(
            centerX,
            centerY,
            glowRadius,
            intArrayOf(withAlpha(blue, 82), withAlpha(mint, 32), Color.TRANSPARENT),
            floatArrayOf(0f, 0.58f, 1f),
            Shader.TileMode.CLAMP,
        )
        starPaint.shader = LinearGradient(
            centerX - starRadius,
            centerY - starRadius,
            centerX + starRadius,
            centerY + starRadius,
            intArrayOf(blueLight, blue, mint, mintLight),
            floatArrayOf(0f, 0.45f, 0.8f, 1f),
            Shader.TileMode.CLAMP,
        )
        coreGlowPaint.shader = RadialGradient(
            centerX,
            centerY,
            starRadius * 0.42f,
            intArrayOf(withAlpha(white, 220), withAlpha(white, 0)),
            floatArrayOf(0f, 1f),
            Shader.TileMode.CLAMP,
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (starRadius <= 0f) return

        val wave = (0.5 + 0.5 * sin(2.0 * PI * 3.0 * phase - PI / 2.0)).toFloat()
        val glowAlpha = 0.72f + 0.28f * wave
        val starScale = 1f + 0.045f * wave
        val starSpin = 2f * sin(2.0 * PI * 3.0 * phase).toFloat()

        // 呼吸光晕
        glowPaint.alpha = (255 * glowAlpha).toInt()
        canvas.drawCircle(centerX, centerY, glowRadius, glowPaint)

        // 两条旋转椭圆轨道：轨道 A 蓝、轨道 B 薄荷绿
        drawOrbit(
            canvas = canvas,
            angleDeg = -24f + 360f * phase,
            radius = orbitRadiusA,
            flatten = 0.42f,
            lineColor = blue,
            dotColor = blue,
            dotAngles = floatArrayOf(-PI.toFloat() / 2f, 2.2f, 4.2f),
        )
        drawOrbit(
            canvas = canvas,
            angleDeg = 28f - 720f * phase,
            radius = orbitRadiusB,
            flatten = 0.5f,
            lineColor = mint,
            dotColor = mint,
            dotAngles = floatArrayOf(PI.toFloat() / 2f, 3.7f, 5.6f),
        )

        // 八角星外发光
        starHaloPaint.color = withAlpha(blue, (50 * glowAlpha).toInt())
        canvas.save()
        canvas.scale(starScale * 1.34f, starScale * 1.34f, centerX, centerY)
        canvas.drawPath(starPath, starHaloPaint)
        canvas.restore()

        // 渐变八角星（轻微呼吸 + 摆动）
        canvas.save()
        canvas.rotate(starSpin, centerX, centerY)
        canvas.scale(starScale, starScale, centerX, centerY)
        canvas.drawPath(starPath, starPaint)
        canvas.restore()

        // 中心白点
        coreGlowPaint.alpha = (225 * glowAlpha).toInt()
        canvas.drawCircle(centerX, centerY, starRadius * 0.4f, coreGlowPaint)
        corePaint.color = withAlpha(white, 236)
        canvas.drawCircle(centerX, centerY, maxOf(1.8f * density, starRadius * 0.062f), corePaint)
    }

    private fun drawOrbit(
        canvas: Canvas,
        angleDeg: Float,
        radius: Float,
        flatten: Float,
        lineColor: Int,
        dotColor: Int,
        dotAngles: FloatArray,
    ) {
        canvas.save()
        canvas.rotate(angleDeg, centerX, centerY)

        orbitPaint.color = withAlpha(lineColor, 76)
        canvas.save()
        canvas.scale(1f, flatten, centerX, centerY)
        canvas.drawCircle(centerX, centerY, radius, orbitPaint)
        canvas.restore()

        for (index in dotAngles.indices) {
            val angle = dotAngles[index].toDouble()
            val x = centerX + (radius * cos(angle)).toFloat()
            val y = centerY + (radius * flatten * sin(angle)).toFloat()
            val mainDot = index == 0
            val dotRadius = (if (mainDot) 2.4f else 1.5f) * density
            dotPaint.color = withAlpha(dotColor, if (mainDot) 38 else 20)
            canvas.drawCircle(x, y, dotRadius * 3.4f, dotPaint)
            dotPaint.color = withAlpha(dotColor, if (mainDot) 232 else 110)
            canvas.drawCircle(x, y, dotRadius, dotPaint)
        }
        canvas.restore()
    }

    private fun buildStarPath() {
        starPath.reset()
        val spikes = 8
        val innerRadius = starRadius * 0.34f
        for (index in 0 until spikes * 2) {
            val angle = -PI / 2.0 + index * PI / spikes
            val radius = if (index % 2 == 0) starRadius else innerRadius
            val x = centerX + (radius * cos(angle)).toFloat()
            val y = centerY + (radius * sin(angle)).toFloat()
            if (index == 0) starPath.moveTo(x, y) else starPath.lineTo(x, y)
        }
        starPath.close()
    }

    private fun startAnimation() {
        if (animator?.isRunning == true) return
        val valueAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = LOOP_MS
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener { animation ->
                phase = animation.animatedValue as Float
                invalidate()
            }
        }
        animator = valueAnimator
        valueAnimator.start()
    }

    private fun stopAnimation() {
        animator?.cancel()
        animator = null
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        startAnimation()
    }

    override fun onDetachedFromWindow() {
        stopAnimation()
        super.onDetachedFromWindow()
    }

    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        if (visibility == VISIBLE && isAttachedToWindow) {
            startAnimation()
        } else {
            stopAnimation()
        }
    }

    private fun withAlpha(color: Int, alpha: Int): Int =
        Color.argb(alpha.coerceIn(0, 255), Color.red(color), Color.green(color), Color.blue(color))

    companion object {
        /** 15s 一个循环：轨道 A 一圈、轨道 B 两圈、呼吸三次，首尾无缝。 */
        private const val LOOP_MS = 15_000L
    }
}
