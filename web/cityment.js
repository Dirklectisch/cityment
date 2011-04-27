var Cityment = Cityment || {};

Cityment.Bars = function(data) {
  var SCALE = 12;
  var list = $('#main ul');

  this.draw = function() {
    list.empty();
    for (var i = 0; i < data.length; i++) {
      var bar = $('<li>'),
          label = $('<span class="label">').text(data[i].area).appendTo(bar),
          score = $('<span class="score">').text(data[i].score),
          width = data[i].score * SCALE;

      list.append(bar);
      bar.css('width', Math.abs(width));
      if (width < 0) {
        score.appendTo(label);
        bar.addClass('negative')
           .css('left', width);
        label.css('left', -width);
      }
      else {
        score.prependTo(label);
        bar.addClass('positive');
        label.css('left', -label.outerWidth());
      }
    }
  };

  this.clear = function() {
    $('li', list).each(function() {
      var bar = $(this);
      $('.label', bar).hide('fast');
      bar.animate({ width: 0, left: 0 }, 500, function() {
        list.empty();
      });
    });
  };
};
var scores = [
  { 'area': 'Nijmegen', 'score': 30 },
  { 'area': 'Amsterdam', 'score': 20 },
  { 'area': 'Utrecht', 'score': 16 },
  { 'area': 'Groningen', 'score': -2 },
  { 'area': 'Den haag', 'score': -4 },
  { 'area': 'Maastricht', 'score': -10 },
];

$(document).ready(function() {
  bars = new Cityment.Bars(scores);
  bars.draw();
});