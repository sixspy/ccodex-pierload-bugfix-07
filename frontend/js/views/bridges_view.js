export const bridgesViewTemplate = `
<section class="panel">
  <h2>地磅桥登记</h2>
  <p class="hint">登记港区地磅额定毛重与轴数上限，供车道阈值引用。</p>
  <div class="form-row">
    <div><label>地磅编码</label><input v-model="bridgeForm.bridge_code"/></div>
    <div><label>港区</label><input v-model="bridgeForm.pier_zone"/></div>
    <div><label>名称</label><input v-model="bridgeForm.name"/></div>
    <div><label>额定毛重(吨)</label><input v-model.number="bridgeForm.max_gross_t" type="number"/></div>
    <div><label>轴数上限</label><input v-model.number="bridgeForm.axle_limit" type="number"/></div>
  </div>
  <div class="actions">
    <button @click="createBridge">登记地磅</button>
    <button class="secondary" @click="refresh">刷新</button>
  </div>
  <table class="data-table">
    <thead><tr><th>编码</th><th>港区</th><th>名称</th><th>额定量程</th><th>轴限</th><th>状态</th><th>校准有效期</th><th>校准</th><th></th></tr></thead>
    <tbody>
      <tr v-for="b in bridges" :key="b.id">
        <td>{{ b.bridge_code }}</td>
        <td>{{ b.pier_zone }}</td>
        <td>{{ b.name }}</td>
        <td>{{ b.max_gross_t }}t</td>
        <td>{{ b.axle_limit }}</td>
        <td><span class="badge" :class="b.status==='运行'?'pass':'warn'">{{ b.status }}</span></td>
        <td class="mono" :class="b.calibration_ok ? '' : 'recon-warn'">{{ b.calibration_valid_until || '未登记' }}</td>
        <td><span class="badge" :class="b.calibration_ok ? 'pass' : 'fail'">{{ b.calibration_state || (b.calibration_ok ? '有效' : '过期') }}</span></td>
        <td><button class="mini-btn" @click="loadBridgeDetail(b.id)">车道</button></td>
      </tr>
    </tbody>
  </table>
  <div v-if="bridgeDetail" class="detail-box">
    <h3>{{ bridgeDetail.bridge.name }} · {{ bridgeDetail.bridge.bridge_code }}</h3>
    <p>在港票 {{ bridgeDetail.active_tickets }} · 车道 {{ bridgeDetail.lanes.length }} 条</p>
    <p :class="bridgeDetail.calibration_ok ? 'recon-ok' : 'recon-warn'">
      校准 {{ bridgeDetail.calibration_ok ? '有效' : '过期/未登记' }}
      · 上次检定 {{ bridgeDetail.bridge.calibration_date || '—' }}
      · 有效期至 {{ bridgeDetail.bridge.calibration_valid_until || '—' }}
    </p>
    <p v-if="!bridgeDetail.calibration_ok" class="recon-warn">校准过期，建票口将拒写；请先完成校准再放行过磅。</p>
  </div>
</section>
`;