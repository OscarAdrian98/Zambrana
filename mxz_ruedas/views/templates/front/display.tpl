{extends file='page.tpl'}

{block name='page_content'}
<script type="text/javascript">
    // Define la base de la URL para las imágenes en una variable global de JavaScript
    var basePath = '{$module_dir}img/';
</script>
<div class="body-configurador">
    <div class="container container-configurador mt-5">
        <div class="row row-configurador">
            <div class="col-lg-3 configurator">
                <div class="card mb-3">
                    <div class="card-header">Modelos</div>
                    <div class="card-body d-flex flex-wrap" id="model">
                        <!-- Modelos de moto -->
                        <div class="model-square" data-value="husqvarna" title="Husqvarna"
                            style="background-image: url('{$module_dir}img/Modelos-logo/husqvarna.png');"></div>
                        <div class="model-square" data-value="kawasaki" title="Kawasaki"
                            style="background-image: url('{$module_dir}img/Modelos-logo/kawasaki.png');"></div>
                        <div class="model-square" data-value="honda" title="Honda"
                            style="background-image: url('{$module_dir}img/Modelos-logo/honda.png');"></div>
                        <div class="model-square" data-value="ktm" title="KTM"
                            style="background-image: url('{$module_dir}img/Modelos-logo/ktm.png');"></div>
                        <div class="model-square" data-value="sherco" title="Sherco"
                            style="background-image: url('{$module_dir}img/Modelos-logo/sherco.png');"></div>
                        <div class="model-square" data-value="beta" title="Beta"
                            style="background-image: url('{$module_dir}img/Modelos-logo/beta.png');"></div>
                        <div class="model-square" data-value="gasgas" title="Gasgas"
                            style="background-image: url('{$module_dir}img/Modelos-logo/gasgas.png');"></div>
                        <div class="model-square" data-value="yamaha" title="Yamaha"
                            style="background-image: url('{$module_dir}img/Modelos-logo/yamaha.png');"></div>
                        <div class="model-square" data-value="suzuki" title="Suzuki"
                            style="background-image: url('{$module_dir}img/Modelos-logo/suzuki.png');"></div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">Componentes</div>
                    <div class="card-body">
                        <!-- Aros -->
                        <label for="rim"><img src="{$module_dir}img/Iconos/icono-aro.jpg" alt="Icono Aro">Aros: <span
                                id="rim-color-name" class="color-name"></span></label>
                        <div class="color-selector d-flex flex-wrap" id="rim"
                            style="border-bottom: 1px solid #ccc; padding-bottom: 10px; margin-bottom: 10px;">
                            <div class="color-square" data-value="a60" style="background-color: #111111;" title="A60">
                            </div>
                            <div class="color-square" data-value="plata" style="background-color: #848482;"
                                title="Plata"></div>
                            <div class="color-square" data-value="azul" style="background-color: #0000FF;" title="Azul">
                            </div>
                            <div class="color-square" data-value="negro" style="background-color: #000000;"
                                title="Negro"></div>
                            <div class="color-square" data-value="oro" style="background-color: #FFD700;" title="Oro">
                            </div>
                            <div class="color-square" data-value="amarillo" style="background-color: #FFFF00;"
                                title="Amarillo"></div>
                        </div>
                        <!-- Bujes -->
                        <label for="hub"><img src="{$module_dir}img/Iconos/icono-buje.png" alt="Icono Buje">Bujes: <span
                                id="hub-color-name" class="color-name"></span></label>
                        <div class="color-selector d-flex flex-wrap" id="hub"
                            style="border-bottom: 1px solid #ccc; padding-bottom: 10px; margin-bottom: 10px;">
                            <div class="color-square" data-value="plata" style="background-color: #848482;"
                                title="Plata"></div>
                            <div class="color-square" data-value="negro" style="background-color: #000000;"
                                title="Negro"></div>
                            <div class="color-square" data-value="azul" style="background-color: #0000FF;" title="Azul">
                            </div>
                            <div class="color-square" data-value="oro" style="background-color: #FFD700;" title="Oro">
                            </div>
                            <div class="color-square" data-value="amarillo" style="background-color: #FFFF00;"
                                title="Amarillo"></div>
                            <div class="color-square" data-value="rojo" style="background-color: #FF0000;" title="Rojo">
                            </div>
                            <div class="color-square" data-value="naranja" style="background-color: #FFA500;"
                                title="Naranja"></div>
                            <div class="color-square" data-value="verde" style="background-color: #008000;"
                                title="Verde"></div>
                            <div class="color-square" data-value="magnesio" style="background-color: #964B00;"
                                title="Magnesio"></div>
                            <div class="color-square" data-value="titanio" style="background-color: #808080;"
                                title="Titanio"></div>
                        </div>
                        <!-- Radios -->
                        <label for="spoke"><img src="{$module_dir}img/Iconos/icono-radio.jpg" alt="Icono Radio">Radios:
                            <span id="spoke-color-name" class="color-name"></span></label>
                        <div class="color-selector d-flex flex-wrap" id="spoke"
                            style="border-bottom: 1px solid #ccc; padding-bottom: 10px; margin-bottom: 10px;">
                            <div class="color-square" data-value="negro" style="background-color: #000000;"
                                title="Negro"></div>
                            <div class="color-square" data-value="plata" style="background-color: #848482;"
                                title="Plata"></div>
                        </div>
                        <!-- Tuercas -->
                        <label for="nipple"><img src="{$module_dir}img/Iconos/icono-tuercas.jpg"
                                alt="Icono Tuercas">Tuercas: <span id="nipple-color-name"
                                class="color-name"></span></label>
                        <div class="color-selector d-flex flex-wrap" id="nipple"
                            style="border-bottom: 1px solid #ccc; padding-bottom: 10px; margin-bottom: 10px;">
                            <div class="color-square" data-value="plata" style="background-color: #848482;"
                                title="Plata"></div>
                            <div class="color-square" data-value="negro" style="background-color: #000000;"
                                title="Negro"></div>
                            <div class="color-square" data-value="azul" style="background-color: #0000FF;" title="Azul">
                            </div>
                            <div class="color-square" data-value="oro" style="background-color: #FFD700;" title="Oro">
                            </div>
                            <div class="color-square" data-value="rojo" style="background-color: #FF0000;" title="Rojo">
                            </div>
                            <div class="color-square" data-value="naranja" style="background-color: #FFA500;"
                                title="Naranja"></div>
                            <div class="color-square" data-value="verde" style="background-color: #008000;"
                                title="Verde"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-lg-9 preview">
                <canvas id="configImageCanvas" style="border: none;"></canvas>
            </div>
        </div>
    </div>
</div>
<!-- Incluye tu script JavaScript aquí, asegurándote de que es después de definir basePath -->
<script src="{$module_dir}views/js/script.js"></script>
{/block}
